from otel_extensions_pytest import TelemetryOptions


def test_options():
    _ = TelemetryOptions()
    _ = TelemetryOptions(OTEL_SESSION_NAME="otel pytest session")
