import otel_extensions_pytest
import pytest
from typing import Union


def pytest_addoption(parser):
    otel_extensions_pytest.pytest_addoption(parser)


def pytest_configure(config):
    otel_extensions_pytest.pytest_configure(config)
    otel_extensions_pytest.pytest_configure(config)
    otel_extensions_pytest.init_telemetry(config)


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    g = otel_extensions_pytest.pytest_runtest_protocol(item, nextitem)
    next(g)
    yield
    try:
        g.send(None)
    except StopIteration:
        pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    g = otel_extensions_pytest.pytest_runtest_setup(item)
    next(g)
    yield
    try:
        g.send(None)
    except StopIteration:
        pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    g = otel_extensions_pytest.pytest_runtest_call(item)
    next(g)
    yield
    try:
        g.send(None)
    except StopIteration:
        pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    g = otel_extensions_pytest.pytest_runtest_teardown(item)
    next(g)
    yield
    try:
        g.send(None)
    except StopIteration:
        pass


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    g = otel_extensions_pytest.pytest_runtest_makereport(item, call)
    next(g)
    try:
        g.send(report)
    except StopIteration:
        pass


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_runtestloop(session):
    yield
    otel_extensions_pytest.pytest_sessionfinish(session, 0)
    otel_extensions_pytest.pytest_unconfigure(session.config)


def pytest_exception_interact(
    node: Union[pytest.Item, pytest.Collector],  # NOSONAR
    call: pytest.CallInfo,
    report: Union[pytest.CollectReport, pytest.TestReport],
):
    otel_extensions_pytest.pytest_exception_interact(node, call, report)


@pytest.hookimpl()
def pytest_runtest_logreport(report):
    otel_extensions_pytest.pytest_runtest_logreport(report)
