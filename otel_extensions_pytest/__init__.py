import os

from otel_extensions import (
    init_telemetry_provider,
    TelemetryOptions as BaseTelemetryOptions,
    flush_telemetry_data,
    get_tracer
)
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Span, Tracer
import logging
from typing import Optional, Iterator, Union
import traceback
import pytest

DEFAULT_SESSION_NAME = "pytest session"
DEFAULT_SERVICE_NAME = "otel_extensions_pytest"

tracer: Optional[Tracer]
session_span: Optional[Span]
session_span_iterator: Optional[Iterator[Span]]


class TelemetryOptions(BaseTelemetryOptions):
    OTEL_SESSION_NAME: str = DEFAULT_SESSION_NAME


def pytest_addoption(parser):
    """Init command line arguments"""
    group = parser.getgroup(
        "otel-extensions-pytest", "options for OpenTelemetry tracing"
    )
    group.addoption(
        "--otel-endpoint",
        dest="otel_endpoint",
        help="OpenTelemetry collector receiver endpoint",
    )
    group.addoption(
        "--otel-protocol",
        dest="otel_protocol",
        help="Protocol for the collector receiver",
    )
    group.addoption(
        "--otel-processor-type",
        dest="otel_processor_type",
        help="Processor type for traces (batch/simple)",
    )
    group.addoption(
        "--otel-service-name",
        dest="otel_service_name",
        help="OpenTelemetry service name",
    )
    group.addoption(
        "--otel-session-name",
        dest="otel_session_name",
        help="Name for the Main span reported.",
    )
    group.addoption(
        "--otel-traceparent",
        dest="otel_traceparent",
        help="Trace parent.(TRACEPARENT) see https://www.w3.org/TR/trace-context-1/#trace-context-http-headers-format",
        # noqa: E501
    )


def pytest_sessionstart(session):
    """
    Sets up telemetry collection and starts the session span
    """
    global session_span, tracer, session_span_iterator
    options = TelemetryOptions()
    config = session.config
    options.OTEL_EXPORTER_OTLP_ENDPOINT = (
        config.getoption("otel_endpoint") or options.OTEL_EXPORTER_OTLP_ENDPOINT
    )
    options.OTEL_EXPORTER_OTLP_PROTOCOL = (
        config.getoption("otel_protocol") or options.OTEL_EXPORTER_OTLP_PROTOCOL
    )
    options.OTEL_PROCESSOR_TYPE = (
        config.getoption("otel_processor_type") or options.OTEL_PROCESSOR_TYPE
    )
    options.OTEL_SERVICE_NAME = (
        config.getoption("otel_service_name") or options.OTEL_SERVICE_NAME
    )
    options.OTEL_SESSION_NAME = (
        config.getoption("otel_session_name") or options.OTEL_SESSION_NAME
    )
    traceparent = config.getoption("otel_traceparent") or os.environ.get("TRACEPARENT")
    if traceparent:
        os.environ["TRACEPARENT"] = traceparent
    init_telemetry_provider(options)
    tracer = get_tracer(options.OTEL_SESSION_NAME, options.OTEL_SERVICE_NAME)
    session_span = tracer.start_span(
        options.OTEL_SESSION_NAME, record_exception=True, set_status_on_exception=True
    )
    session_span_iterator = trace.use_span(session_span, end_on_exit=True)
    session_span_iterator.__enter__()  # noqa


def pytest_sessionfinish(session, exitstatus):  # noqa: U100
    """Ends the session span with the session outcome"""
    global session_span, session_span_iterator
    if session_span is not None:
        outcome = _exit_code_to_outcome(exitstatus)
        session_span.set_attribute("tests.status", outcome)
        session_span.set_status(_convert_outcome(outcome))
        trace_id = session_span.get_span_context().trace_id
        _logger().info(f"Trace ID for pytest session is {trace_id:32x}")
        session_span_iterator.__exit__(None, None, None)  # noqa
    flush_telemetry_data()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global tracer
    with tracer.start_as_current_span(
        item.name,
        record_exception=True,
        set_status_on_exception=True,
    ) as span:
        span.set_attribute("tests.name", item.name)
        yield


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):  # noqa
    report = yield
    rep = report.get_result()

    if rep.when == "call":
        span = trace.get_current_span()
        status = _convert_outcome(rep.outcome)
        span.set_status(status)
        span.set_attribute("tests.status", rep.outcome)


def pytest_exception_interact(
    node: Union[pytest.Item, pytest.Collector],
    call: pytest.CallInfo,
    report: Union[pytest.CollectReport, pytest.TestReport],
):
    if isinstance(report, pytest.TestReport) and call.excinfo is not None:
        span = trace.get_current_span()
        stack_trace = repr(
            traceback.format_exception(
                call.excinfo.type, call.excinfo.value, call.excinfo.tb
            )
        )
        span.set_attribute("tests.error", stack_trace)


@pytest.hookimpl()
def pytest_runtest_logreport(report):
    if report.failed and report.when == "call":
        span = trace.get_current_span()
        span.set_attribute("tests.stderr", report.capstderr)
        span.set_attribute("tests.stdout", report.capstdout)
        span.set_attribute("tests.duration", getattr(report, "duration", 0.0))


def _logger():
    return logging.getLogger(__name__)


def _convert_outcome(outcome: str) -> Status:
    """Convert from pytest outcome to OpenTelemetry status code"""
    if outcome == "passed":
        return Status(status_code=StatusCode.OK)
    elif (
        outcome == "failed"
        or outcome == "interrupted"
        or outcome == "internal_error"
        or outcome == "usage_error"
        or outcome == "no_tests_collected"
    ):
        return Status(status_code=StatusCode.ERROR)
    else:
        return Status(status_code=StatusCode.UNSET)


def _exit_code_to_outcome(exit_code: int) -> str:
    """convert pytest ExitCode to outcome"""
    if exit_code == 0:
        return "passed"
    elif exit_code == 1:
        return "failed"
    elif exit_code == 2:
        return "interrupted"
    elif exit_code == 3:
        return "internal_error"
    elif exit_code == 4:
        return "usage_error"
    elif exit_code == 5:
        return "no_tests_collected"
    else:
        return "failed"
