import os

from otel_extensions import (
    init_telemetry_provider,
    TelemetryOptions as BaseTelemetryOptions,
    flush_telemetry_data,
    get_tracer,
)
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Span, Tracer
import logging
from typing_extensions import Literal
from typing import Optional, Union, Callable, Iterable, Any
import traceback
import pytest
from _pytest.fixtures import FixtureFunctionMarker
from contextlib import ExitStack, contextmanager
from pydantic import root_validator
from functools import wraps
import inspect

DEFAULT_SESSION_NAME = "pytest session"
DEFAULT_SERVICE_NAME = "otel_extensions_pytest"

tracer: Optional[Tracer]
session_context_stack: Optional[ExitStack] = None


class TelemetryOptions(BaseTelemetryOptions):
    """Settings class holding options for telemetry"""

    OTEL_SESSION_NAME: str = DEFAULT_SESSION_NAME

    @root_validator
    def update_env(cls, values):
        for k, v in values.items():
            if v is not None:
                os.environ[k] = v
        return values

    class Config:
        validate_assignment = True


class InstrumentedFixture:
    """Helper class for wrapping a fixture function"""

    def __init__(
        self,
        fixture: FixtureFunctionMarker,
        span_name: str = None,
        service_name: str = None,
    ):

        self.fixture = fixture
        self.span_name = span_name
        self.service_name = service_name

    def is_generator(self, func: object) -> bool:
        genfunc = inspect.isgeneratorfunction(func)
        return genfunc and not self.iscoroutinefunction(func)

    def iscoroutinefunction(self, func: object) -> bool:
        return inspect.iscoroutinefunction(func) or getattr(
            func, "_is_coroutine", False
        )

    def __call__(self, wrapped_function: Callable) -> Callable:
        @wraps(wrapped_function)
        def new_f(*args, **kwargs):
            module = inspect.getmodule(wrapped_function)
            module_name = __name__
            if module is not None:
                module_name = module.__name__
            span_name = self.span_name or wrapped_function.__qualname__
            if self.is_generator(wrapped_function):
                generator = wrapped_function(*args, **kwargs)
                with get_tracer(
                    module_name, service_name=self.service_name
                ).start_as_current_span(f"{span_name} (setup)"):
                    x = next(generator)
                yield x
                with get_tracer(
                    module_name, service_name=self.service_name
                ).start_as_current_span(f"{span_name} (teardown)"):
                    try:
                        next(generator)
                    except StopIteration:
                        pass
            else:
                with get_tracer(
                    module_name, service_name=self.service_name
                ).start_as_current_span(span_name):
                    # even if the original fixture is not a generator, since we're wrapping it with
                    # this function we turn it into a generator (due to the inclusion of the yield statement in the case
                    # above). Thus, pytest expects us to yield a value and not just return the result of the original
                    # function.
                    yield wrapped_function(*args, **kwargs)

        return self.fixture(new_f)


def instrumented_fixture(
    fixture_function: Optional[Callable] = None,
    *,
    scope: Literal["session", "module", "package", "class", "function"] = "function",
    params: Optional[Iterable[object]] = None,
    autouse: bool = False,
    ids: Optional[
        Union[
            Iterable[Union[None, str, float, int, bool]],
            Callable[[Any], Optional[object]],
        ]
    ] = None,
    name: Optional[str] = None,
    span_name: Optional[str] = None,
) -> Union[FixtureFunctionMarker, Callable]:
    """
    Decorator to enable opentelemetry instrumentation on a pytest fixture.

    When the decorator is used, a child span will be created in the current trace
    context, using the fully-qualified function name as the span name.
    Alternatively, the span name can be set manually by setting the span_name parameter


    :param scope:
        The scope for which this fixture is shared; one of ``"function"``
        (default), ``"class"``, ``"module"``, ``"package"`` or ``"session"``.

        This parameter may also be a callable which receives ``(fixture_name, config)``
        as parameters, and must return a ``str`` with one of the values mentioned above.

        See :ref:`dynamic scope` in the docs for more information.

    :param params:
        An optional list of parameters which will cause multiple invocations
        of the fixture function and all of the tests using it. The current
        parameter is available in ``request.param``.

    :param autouse:
        If True, the fixture func is activated for all tests that can see it.
        If False (the default), an explicit reference is needed to activate
        the fixture.

    :param ids:
        Sequence of ids each corresponding to the params so that they are
        part of the test id. If no ids are provided they will be generated
        automatically from the params.

    :param name:
        The name of the fixture. This defaults to the name of the decorated
        function. If a fixture is used in the same module in which it is
        defined, the function name of the fixture will be shadowed by the
        function arg that requests the fixture; one way to resolve this is to
        name the decorated function ``fixture_<fixturename>`` and then use
        ``@pytest.fixture(name='<fixturename>')``.

    :param span_name:
         optional span name.  Defaults to fully qualified function name of fixture, or the ``name``
         parameter if it is provided

    """
    marker = InstrumentedFixture(
        fixture=FixtureFunctionMarker(
            scope=scope, params=params, autouse=autouse, ids=ids, name=name
        ),
        span_name=span_name,
    )

    if fixture_function:
        return marker(fixture_function)

    return marker


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


def init_telemetry(config: pytest.Config, options: Optional[TelemetryOptions] = None):
    global session_context_stack, tracer
    if session_context_stack is not None:
        _logger().error("init_telemetry can only be called once!")
        return
    if options is None:
        options = TelemetryOptions()
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
    session_context_stack = ExitStack()
    session_context_stack.enter_context(
        tracer.start_as_current_span(
            options.OTEL_SESSION_NAME,
            record_exception=True,
            set_status_on_exception=True,
        )
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """
    Sets up telemetry collection and starts the session span, if not already started previously
    """
    global session_context_stack
    if session_context_stack is None:
        init_telemetry(config)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):  # noqa: U100
    """Sets properties on the session span with the session outcome"""
    session_span = trace.get_current_span()
    if session_span.is_recording():
        outcome = _exit_code_to_outcome(exitstatus)
        session_span.set_attribute("tests.status", outcome)
        session_span.set_status(_convert_outcome(outcome))
        trace_id = session_span.get_span_context().trace_id
        _logger().info(f"Trace ID for pytest session is {trace_id:32x}")


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """Ends the session span"""
    global session_context_stack
    if session_context_stack:
        session_context_stack.close()
    flush_telemetry_data()


@contextmanager
def create_runtest_span(span_name: str, test_name):
    global tracer
    with tracer.start_as_current_span(
        span_name,
        record_exception=True,
        set_status_on_exception=True,
    ) as span:
        span.set_attribute("tests.name", test_name)
        yield


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    with create_runtest_span(item.name, item.name):
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    with create_runtest_span(f"{item.name} (setup)", item.name):
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    with create_runtest_span(f"{item.name} (call)", item.name):
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    with create_runtest_span(f"{item.name} (teardown)", item.name):
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
