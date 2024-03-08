from otel_extensions_pytest import instrumented_fixture


@instrumented_fixture()
def dummy_fixture():
    return 42


@instrumented_fixture
def dummy_fixture_2():
    yield 24


def test_dummy_fixtures(dummy_fixture, dummy_fixture_2):
    assert dummy_fixture == 42
    assert dummy_fixture_2 == 24
