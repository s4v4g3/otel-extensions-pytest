# otel-extensions-pytest: A pytest extension for OpenTelemetry

`otel-extensions-pytest` is a pytest plugin that will automatically instrument a pytest-based test session, 
wrapping the test session in a span and wrapping each test in a child span.

## Dependencies

* Python >= 3.6
* pytest >= 6.2

## Installation
### pip install

You can install through pip using:

```sh
pip install otel-extensions-pytest
```
(you may need to run `pip` with root permission: `sudo pip install otel-extensions-pytest`)


### Setuptools

Install via [Setuptools](http://pypi.python.org/pypi/setuptools).

```sh
python setup.py install --user
```
(or `sudo python setup.py install` to install the package for all users)



## Usage

Enable the plugin by adding
```python
pytest_plugins = ("otel_extensions",)
```
to your `conftest.py`, or by adding the option `-p otel_extensions` to the pytest command line. 

For tracing to be enabled, you need to specify a trace receiver endpoint using the command-line option
`--otel-endpoint` or by setting the environment variable `OTEL_EXPORTER_OTLP_ENDPOINT`.
e.g. `--otel-endpoint http://localhost:4317/`


The full set of options are shown here:

| Command-line Option     | Environment Variable                                                      | Description                                                                                                                                                                      |
|-------------------------|---------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--otel_service_name`   | `OTEL_SERVICE_NAME` | Name of resource/service for traces                                                                                                                                              |
| `--otel_session_name`   | `OTEL_SESSION_NAME` | Name of parent session span                                                                                                                                                      |
| `--otel_endpoint`       | `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP Receiver Endpoint                                                                                                                                                           |
| `--otel_protocol`       | `OTEL_EXPORTER_OTLP_PROTOCOL` | protocol for OTLP receiver (supported: `gprc` , `http/protobuf` , `custom`)                                                                                                      |
| `--otel_processor_type` | `OTEL_PROCESSOR_TYPE` | Span Processor type (batch:  use `BatchSpanProcessor`,    simple: use `SimpleSpanProcessor`                                                                                      |
| `--otel_traceparent`    | `TRACEPARENT` | Parent span id.  Will be injected into current context (useful when running automated tests using the [OpenTelemetry Jenkins](https://plugins.jenkins.io/opentelemetry/) plugin) |
| n/a                     | `OTEL_EXPORTER_OTLP_CERTIFICATE` | path to CA bundle for verifying TLS cert of receiver endpoint                                                                                                                    |
| n/a                     | `OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE` | Custom span exporter class (needed if protocol set to `custom`)                                                                                                                  |

## Additional Features

### `@instrumented_fixture` decorator

You can decorate fixtures by using the `@instrumented_fixture` decorator.  If the fixture is a generator (i.e. has a `yield` statement), separate spans will be created for the setup and teardown phases.


```python
from otel_extensions_pytest import instrumented_fixture

# note: all options of pytest.fixture() are supported (autouse, etc)
@instrumented_fixture(scope="function")
def my_fixture():
    """ Span is automatically created using `my_fixture` as span name """
    return "foo"

@instrumented_fixture(scope="function")
def my_generator_fixture():
    # A span named `my_generator_fixture (setup)` is automatically created for this section
    time.sleep(5)
    
    yield "foo"
    
    # A span named `my_generator_fixture (teardown)` is automatically created for this section
    time.sleep(5)
    
```
