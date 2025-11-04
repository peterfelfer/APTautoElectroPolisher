from apt_polisher.instrumentation.scpi import SCPIPowerSupply


class DummyTransport:
    def __init__(self, responses=None):
        self.commands = []
        self.responses = list(responses or [])

    def write(self, data: str) -> None:
        # Simulate transport adding newline automatically
        if not data.endswith("\n"):
            data += "\n"
        self.commands.append(data)

    def readline(self, timeout=None) -> str:
        if self.responses:
            return self.responses.pop(0)
        return "0"

    def close(self) -> None:
        pass


def test_scpi_power_supply_basic_commands():
    transport = DummyTransport(responses=["MySupply,123", "1.000", "0.500"])
    psu = SCPIPowerSupply(transport=transport, delay_after_set=0.0)

    ident = psu.identify()
    psu.set_voltage(1.234)
    psu.set_current_limit(0.456)
    psu.output(True)
    voltage = psu.measure_voltage()
    current = psu.measure_current()

    assert ident == "MySupply,123"
    assert voltage == 1.0
    assert current == 0.5
    assert "VOLT 1.234000\n" in transport.commands
    assert "CURR 0.456000\n" in transport.commands
    assert "OUTP ON\n" in transport.commands
