"""
fluidnc_client.py
-----------------
A small, robust Python client for controlling a FluidNC/GRBL-compatible CNC over a serial port.

Features
- Connect/disconnect with automatic input flush and firmware banner detection
- Threaded reader that parses lines and dispatches callbacks
- Synchronous `send_gcode()` with optional wait-for-`ok`
- High-throughput streaming with planner-friendly outstanding-OK window
- Real-time controls: soft reset (^X), feed hold (!), cycle start (~), status ('?'), unlock ($X), home ($H)
- Jogging with $J= (relative, G21/G91) with sanity checks
- Status parsing for both GRBL angle-bracket format and JSON-like FluidNC status
- Wait-until-idle and get parser state ($G)
- Clean shutdown and context-manager support

Requires: pyserial
    pip install pyserial
"""

from __future__ import annotations

import threading
import time
import sys
import json
import re
import queue
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Dict, Any

try:
    import serial  # pyserial
    from serial import Serial
except Exception as e:
    raise RuntimeError("pyserial is required: pip install pyserial") from e


# ----------------------------- Data structures -----------------------------

@dataclass
class CNCStatus:
    state: str = "Unknown"            # e.g., "Idle", "Run", "Hold", "Alarm"
    mpos: Optional[List[float]] = None  # machine position [X,Y,Z,...]
    wpos: Optional[List[float]] = None  # work position [X,Y,Z,...]
    feed: Optional[float] = None        # current feed (mm/min)
    spindle: Optional[float] = None     # current spindle RPM
    overrides: Optional[Dict[str, int]] = None  # feed/spindle overrides
    raw: Optional[str] = None           # raw status line


# ----------------------------- Client class --------------------------------

class FluidNCClient:
    """Serial client for FluidNC/GRBL-like controllers."""

    def __init__(self,
                 port: str,
                 baud: int = 115200,
                 timeout: float = 0.05,
                 on_line: Optional[Callable[[str], None]] = None,
                 on_ok: Optional[Callable[[], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None,
                 on_status: Optional[Callable[[CNCStatus], None]] = None,
                 ):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.on_line = on_line
        self.on_ok = on_ok
        self.on_error = on_error
        self.on_status = on_status

        self.ser: Optional[Serial] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_reader = threading.Event()

        # Flow control
        self._ok_cv = threading.Condition()
        self._inflight = 0

        # Last status cache
        self._last_status: Optional[CNCStatus] = None
        self._parser_state_queue: "queue.Queue[str]" = queue.Queue()

    # ------------------------- Connection management ------------------------

    def connect(self, wait_banner: bool = True, banner_timeout: float = 2.0) -> None:
        """Open serial port and start reader thread."""
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
        # Flush any residual
        self.flush_input()
        self._stop_reader.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        if wait_banner:
            # Many firmwares print a banner like "Grbl ...", "FluidNC ..."
            t0 = time.time()
            while time.time() - t0 < banner_timeout:
                if self._last_status is not None:
                    break
                time.sleep(0.05)
            # Not strictly required

    def close(self) -> None:
        """Stop reader and close port."""
        self._stop_reader.set()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ------------------------------- Reader ---------------------------------

    def _reader_loop(self):
        buf = bytearray()
        while not self._stop_reader.is_set():
            try:
                if not self.ser or not self.ser.is_open:
                    break
                chunk = self.ser.read(256)
                if chunk:
                    buf.extend(chunk)
                    while b'\n' in buf:
                        line, _, buf = buf.partition(b'\n')
                        line = line.strip().decode(errors='ignore')
                        if not line:
                            continue
                        self._handle_line(line)
                else:
                    time.sleep(0.005)
            except Exception as e:
                # Report error and attempt to continue; break if port died
                if self.on_error:
                    self.on_error(f"Reader error: {e!r}")
                time.sleep(0.1)

    def _handle_line(self, line: str) -> None:
        """Parse common GRBL/FluidNC responses and dispatch callbacks."""
        # Debug callback for all lines
        if self.on_line:
            try:
                self.on_line(line)
            except Exception:
                pass

        # OK / ERROR
        if line.lower() == "ok":
            with self._ok_cv:
                self._inflight = max(0, self._inflight - 1)
                self._ok_cv.notify_all()
            if self.on_ok:
                try: self.on_ok()
                except Exception: pass
            return
        if line.lower().startswith("error") or line.lower().startswith("alarm"):
            with self._ok_cv:
                self._inflight = max(0, self._inflight - 1)
                self._ok_cv.notify_all()
            if self.on_error:
                try: self.on_error(line)
                except Exception: pass
            return

        # Status reports: angle-bracket format <Idle|MPos:...|...>
        if line.startswith("<") and line.endswith(">"):
            st = self._parse_angle_status(line)
            self._last_status = st
            if self.on_status:
                try: self.on_status(st)
                except Exception: pass
            return

        # JSON-like status (FluidNC can be configured to output JSON)
        if line.startswith("{") and line.endswith("}"):
            st = self._parse_json_status(line)
            if st:
                self._last_status = st
                if self.on_status:
                    try: self.on_status(st)
                    except Exception: pass
            return

        # Parser state lines typically look like "[GC:G0 G54 ...]"
        if line.startswith("[GC:") or line.startswith("[gc:"):
            try:
                # Keep queue short to avoid stale buildup
                while self._parser_state_queue.qsize() > 5:
                    self._parser_state_queue.get_nowait()
            except queue.Empty:
                pass
            self._parser_state_queue.put(line)
            # Fall through so on_line still receives it

        # Messages, parser state, etc. are passed to on_line (already done)

    # ------------------------------ Parsers ---------------------------------

    _kv_re = re.compile(r"([A-Za-z]+):([^|]+)")

    def _parse_angle_status(self, s: str) -> CNCStatus:
        # Example: <Idle|MPos:0.000,0.000,-5.000|FS:0,0|WCO:0.000,0.000,0.000>
        inner = s.strip("<>")
        parts = inner.split("|")
        state = parts[0]
        kv = {}
        for p in parts[1:]:
            m = self._kv_re.match(p)
            if m:
                kv[m.group(1)] = m.group(2)

        def _flt_list(val: str) -> List[float]:
            return [float(x) for x in val.split(",")] if val else []

        st = CNCStatus(state=state, raw=s)
        if "MPos" in kv:
            st.mpos = _flt_list(kv["MPos"])
        if "WPos" in kv:
            st.wpos = _flt_list(kv["WPos"])
        if "FS" in kv:
            fs = _flt_list(kv["FS"])
            if len(fs) >= 1: st.feed = fs[0]
            if len(fs) >= 2: st.spindle = fs[1]
        if "Ov" in kv:
            ov = [int(x) for x in kv["Ov"].split(",")]
            st.overrides = {"feed": ov[0] if len(ov) > 0 else None,
                            "rapid": ov[1] if len(ov) > 1 else None,
                            "spindle": ov[2] if len(ov) > 2 else None}
        return st

    def _parse_json_status(self, s: str) -> Optional[CNCStatus]:
        try:
            j = json.loads(s)
        except Exception:
            return None
        st = CNCStatus(raw=s)
        # Best-effort mapping; keys vary by config
        st.state = j.get("state", j.get("sr", {}).get("state", "Unknown"))
        st.mpos = j.get("mpos") or j.get("sr", {}).get("mpos")
        st.wpos = j.get("wpos") or j.get("sr", {}).get("wpos")
        fs = j.get("fs") or j.get("sr", {}).get("fs")
        if isinstance(fs, list) and len(fs) >= 1:
            st.feed = fs[0]
            st.spindle = fs[1] if len(fs) > 1 else None
        return st

    # ------------------------------ Utilities --------------------------------

    def flush_input(self):
        if self.ser and self.ser.in_waiting:
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass

    def write_line(self, line: str) -> None:
        """Write a single line with newline termination (no waiting)."""
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial not open")
        if not line.endswith("\n"):
            line += "\n"
        self.ser.write(line.encode())

    # --------------------------- G-code senders ------------------------------

    def send_gcode(self, line: str, wait_ok: bool = True, timeout: float = 5.0) -> None:
        """Send one G-code line; optionally block until 'ok'/'error' observed."""
        with self._ok_cv:
            self._inflight += 1
        self.write_line(line)
        if wait_ok:
            self._wait_inflight_delta(-1, timeout=timeout)

    def stream_gcode(self,
                     lines: Iterable[str],
                     max_outstanding: int = 12,
                     progress: Optional[Callable[[int], None]] = None,
                     per_line_timeout: float = 5.0) -> None:
        """
        High-throughput streaming: keep up to 'max_outstanding' lines queued, decrementing on each 'ok'/'error'.
        """
        sent = 0
        for line in lines:
            # Block if too many un-acked lines
            with self._ok_cv:
                while self._inflight >= max_outstanding:
                    self._ok_cv.wait(timeout=0.5)
            self.send_gcode(line, wait_ok=False)
            sent += 1
            if progress:
                try: progress(sent)
                except Exception: pass

        # Drain remaining inflight
        with self._ok_cv:
            deadline = time.time() + per_line_timeout * max(1, self._inflight)
            while self._inflight > 0 and time.time() < deadline:
                self._ok_cv.wait(timeout=0.2)
            if self._inflight > 0:
                raise TimeoutError(f"Timed out waiting for {self._inflight} pending 'ok' responses")

    def _wait_inflight_delta(self, delta: int, timeout: float) -> None:
        """Wait until inflight has decreased by |delta| or timeout."""
        target = None
        with self._ok_cv:
            target = self._inflight + delta
        t0 = time.time()
        while True:
            with self._ok_cv:
                if self._inflight <= target:
                    return
                remaining = timeout - (time.time() - t0)
                if remaining <= 0:
                    raise TimeoutError("Timeout waiting for 'ok'")
                self._ok_cv.wait(timeout=min(0.2, remaining))

    # -------------------------- Real-time commands ---------------------------

    def soft_reset(self):
        """Ctrl-X (0x18) — resets the controller (clears planner, states)."""
        if not self.ser: return
        self.ser.write(b'\x18')
        # Allow firmware to reboot
        time.sleep(0.2)
        self.flush_input()
        with self._ok_cv:
            self._inflight = 0
            self._ok_cv.notify_all()

    def feed_hold(self):
        if not self.ser: return
        self.ser.write(b'!')

    def cycle_start(self):
        if not self.ser: return
        self.ser.write(b'~')

    def status_query(self):
        if not self.ser: return
        self.ser.write(b'?')

    def unlock(self):
        self.send_gcode("$X", wait_ok=True)

    def home(self):
        self.send_gcode("$H", wait_ok=True)

    def parser_state(self, timeout: float = 1.0) -> str:
        """Send $G and return the next line that looks like parser state."""
        self.flush_input()
        # Drop any stale parser-state replies before querying again
        while not self._parser_state_queue.empty():
            try:
                self._parser_state_queue.get_nowait()
            except queue.Empty:
                break
        self.send_gcode("$G", wait_ok=False)
        try:
            return self._parser_state_queue.get(timeout=timeout)
        except queue.Empty:
            return ""

    def wait_until_idle(self, poll_hz: float = 5.0, timeout: float = 60.0) -> CNCStatus:
        """Poll status until controller reports Idle or timeout. Returns last status."""
        period = max(0.01, 1.0 / poll_hz)
        t0 = time.time()
        last: Optional[CNCStatus] = None
        while time.time() - t0 < timeout:
            self.status_query()
            time.sleep(period)
            last = self._last_status or last
            if last and last.state.lower() == "idle":
                return last
        return last or CNCStatus(state="Unknown")

    # ------------------------------ Jogging ----------------------------------

    def jog(self, dx: float = 0, dy: float = 0, dz: float = 0,
            feed_mm_min: float = 600.0,
            safe_limits: Optional[Dict[str, tuple]] = None) -> None:
        """
        Issue a GRBL/FluidNC '$J=' jog using relative coordinates.
        safe_limits: optional {"X": (min,max), "Y": (...), "Z": (...)} to reject huge jogs
        """
        # Sanity check
        moves = {"X": dx, "Y": dy, "Z": dz}
        if safe_limits:
            for ax, d in moves.items():
                if ax in safe_limits and d is not None:
                    mn, mx = safe_limits[ax]
                    if d < mn or d > mx:
                        raise ValueError(f"Jog {ax}{d} out of safe_limits {mn}..{mx}")

        parts = [f"$J=G91 G21"]
        for ax, d in moves.items():
            if abs(float(d)) > 1e-9:
                parts.append(f"{ax}{float(d):.4f}")
        parts.append(f"F{float(feed_mm_min):.2f}")
        cmd = " ".join(parts)
        # Jog commands do not return a normal 'ok' sequence; don't wait.
        self.send_gcode(cmd, wait_ok=False)

    # ------------------------------- Helpers ---------------------------------

    @property
    def last_status(self) -> Optional[CNCStatus]:
        return self._last_status


# ------------------------------ Example usage -------------------------------

if __name__ == "__main__":
    # Minimal demo: prints all lines & periodic parsed status, then sends a move.
    def print_line(s): print(f"[LINE] {s}")
    def print_ok(): print("[OK]")
    def print_err(e): print(f"[ERR] {e}")
    def print_status(st: CNCStatus): print(f"[STATUS] {st.state} mpos={st.mpos} feed={st.feed}")

   # port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    port = "/dev/tty.usbserial-210"

    with FluidNCClient(port, baud=115200,
                       on_line=print_line,
                       on_ok=print_ok,
                       on_error=print_err,
                       on_status=print_status) as cnc:
        print("Connected.")
        cnc.unlock()
        cnc.status_query()
        time.sleep(0.2)
        # Simple move (adapt to your machine safe Z)
        cnc.send_gcode("G21 G90")
        cnc.send_gcode("G0 Z10.000")
        cnc.wait_until_idle(poll_hz=5, timeout=10)
        print("Done.")
