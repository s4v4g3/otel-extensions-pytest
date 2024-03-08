from otel_extensions_pytest import _convert_outcome, _exit_code_to_outcome, _logger
from opentelemetry.trace import StatusCode


def test_convert_outcome():
    assert _convert_outcome("passed").status_code == StatusCode.OK
    assert _convert_outcome("failed").status_code == StatusCode.ERROR
    assert _convert_outcome("skipped").status_code == StatusCode.UNSET


def test_exit_code_to_outcome():
    assert _exit_code_to_outcome(0) == "passed"
    assert _exit_code_to_outcome(1) == "failed"
    assert _exit_code_to_outcome(2) == "interrupted"
    assert _exit_code_to_outcome(3) == "internal_error"
    assert _exit_code_to_outcome(4) == "usage_error"
    assert _exit_code_to_outcome(5) == "no_tests_collected"
    assert _exit_code_to_outcome(6) == "failed"


def test_logger():
    l = _logger()
    assert l.name == "otel_extensions_pytest"
