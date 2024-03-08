import otel_extensions_pytest
import pytest


def pytest_addoption(parser):
    otel_extensions_pytest.pytest_addoption(parser)


def pytest_configure(config):
    otel_extensions_pytest.pytest_configure(config)
    otel_extensions_pytest.pytest_configure(config)
    otel_extensions_pytest.init_telemetry(config)


def pytest_sessionfinish(session, exitstatus):
    otel_extensions_pytest.pytest_sessionfinish(session, exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    otel_extensions_pytest.pytest_unconfigure(config)
