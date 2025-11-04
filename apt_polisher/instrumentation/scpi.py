"""SCPI helpers for controlling lab instruments such as power supplies."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Optional, Protocol, TYPE_CHECKING

try:  # pragma: no cover - import guard for optional dependency
    from serial import Serial  # type: ignore
except ImportError:  # pragma: no cover
    Serial = None  # type: ignore


class SCPITransport(Protocol):
    """Minimal interface for SCPI transports."""

    def write(self, data: str) -> None:
        ...

    def readline(self, timeout: Optional[float] = None) -> str:
        ...

    def close(self) -> None:
        ...


class SocketSCPITransport:
    """SCPI transport using a TCP socket (e.g., LAN-connected instruments)."""

    def __init__(self, host: str, port: int = 5025, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)
        self._buffer = bytearray()

    def write(self, data: str) -> None:
        payload = data.encode("ascii")
        if not data.endswith("\n"):
            payload += b"\n"
        self._sock.sendall(payload)

    def readline(self, timeout: Optional[float] = None) -> str:
        if timeout is not None:
            self._sock.settimeout(timeout)
        while b"\n" not in self._buffer:
            chunk = self._sock.recv(4096)
            if not chunk:
                break
            self._buffer.extend(chunk)
        line, _, rest = self._buffer.partition(b"\n")
        self._buffer = bytearray(rest)
        return line.decode("ascii", errors="ignore").strip()

    def close(self) -> None:
        try:
            self._sock.close()
        finally:
            self._buffer.clear()


class SerialSCPITransport:
    """SCPI transport using an RS-232/USB serial connection."""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 1.0) -> None:
        if Serial is None:
            raise RuntimeError("pyserial is required for SerialSCPITransport. Install pyserial and retry.")
        self._serial = Serial(port=port, baudrate=baudrate, timeout=timeout)

    def write(self, data: str) -> None:
        if not data.endswith("\n"):
            data += "\n"
        self._serial.write(data.encode("ascii"))

    def readline(self, timeout: Optional[float] = None) -> str:
        if timeout is not None:
            self._serial.timeout = timeout
        line = self._serial.readline().decode("ascii", errors="ignore").strip()
        return line

    def close(self) -> None:
        self._serial.close()


class PowerSupply(Protocol):
    """High-level power-supply control interface."""

    def set_voltage(self, volts: float) -> None:
        ...

    def set_current_limit(self, amps: float) -> None:
        ...

    def output(self, enabled: bool) -> None:
        ...

    def measure_voltage(self) -> float:
        ...

    def measure_current(self) -> float:
        ...

    def identify(self) -> str:
        ...


@dataclass
class SCPIPowerSupply:
    """SCPI-based power-supply controller."""

    transport: SCPITransport
    delay_after_set: float = 0.05

    def close(self) -> None:
        self.transport.close()

    # -- factory helpers -------------------------------------------------
    @classmethod
    def from_tcp(cls, host: str, port: int = 5025, timeout: float = 2.0) -> "SCPIPowerSupply":
        return cls(SocketSCPITransport(host=host, port=port, timeout=timeout))

    @classmethod
    def from_serial(cls, port: str, baudrate: int = 9600, timeout: float = 1.0) -> "SCPIPowerSupply":
        return cls(SerialSCPITransport(port=port, baudrate=baudrate, timeout=timeout))

    # -- basic helpers ---------------------------------------------------
    def _write(self, command: str) -> None:
        self.transport.write(command)

    def _query(self, command: str, timeout: Optional[float] = None) -> str:
        self._write(command)
        return self.transport.readline(timeout=timeout)

    # -- power-supply API ------------------------------------------------
    def identify(self) -> str:
        return self._query("*IDN?")

    def set_voltage(self, volts: float) -> None:
        self._write(f"VOLT {volts:.6f}")
        time.sleep(self.delay_after_set)

    def set_current_limit(self, amps: float) -> None:
        self._write(f"CURR {amps:.6f}")
        time.sleep(self.delay_after_set)

    def output(self, enabled: bool) -> None:
        self._write(f"OUTP {'ON' if enabled else 'OFF'}")

    def measure_voltage(self) -> float:
        return _to_float(self._query("MEAS:VOLT?"))

    def measure_current(self) -> float:
        return _to_float(self._query("MEAS:CURR?"))


def _to_float(value: str) -> float:
    try:
        return float(value.strip())
    except ValueError as exc:
        raise RuntimeError(f"Failed to parse float from SCPI response: {value!r}") from exc
