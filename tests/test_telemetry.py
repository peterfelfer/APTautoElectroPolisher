from pathlib import Path

from apt_polisher.telemetry import TelemetryLogger, TelemetryRecord, TelemetrySeries


def test_telemetry_series_append_and_dict():
    series = TelemetrySeries(max_points=3)
    records = [
        TelemetryRecord(timestamp=1.0, voltage=1.1, current=0.5, temperature=22.0),
        TelemetryRecord(timestamp=2.0, voltage=1.2, current=0.6, temperature=22.5),
        TelemetryRecord(timestamp=3.0, voltage=1.3, current=0.7, temperature=23.0),
        TelemetryRecord(timestamp=4.0, voltage=1.4, current=0.8, temperature=23.5),
    ]
    series.extend(records)

    data = series.to_dict_of_lists()
    assert data["timestamp"] == [2.0, 3.0, 4.0]
    assert data["voltage"][-1] == 1.4
    assert series.latest().current == 0.8


def test_telemetry_logger(tmp_path: Path):
    log_path = tmp_path / "log.csv"
    logger = TelemetryLogger(log_path)
    with logger:
        logger.log(TelemetryRecord(timestamp=1.234, voltage=1.0, current=None, temperature=25.0))
        logger.log_many(
            [
                TelemetryRecord(timestamp=2.0, voltage=1.1, current=0.5, temperature=26.0),
                TelemetryRecord(timestamp=3.0, voltage=None, current=0.6, temperature=None),
            ]
        )

    text = log_path.read_text().strip().splitlines()
    assert text[0] == "timestamp,voltage,current,temperature"
    assert text[1].startswith("1.234")
    assert text[-1].split(",")[1] == ""
