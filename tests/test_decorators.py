import otel_extensions_pytest


def test_nothing():
    assert otel_extensions_pytest.DEFAULT_SESSION_NAME == "pytest session"
