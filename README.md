# Pytest Autocap

Pytest Autocap, if enabled, will automatically capture the output written to `stdout` and `stderr`, writing it down into an output directory of your choosing.

Each test is assigned a unique output directory in a way closely following how pytest refers to tests, e.g. `tests/package_b/test_module_b.py::TestModBClass::test_two[2]` is located in `tests/package_b/test_module_b/TestModBClass/test_two[2]` inside the output directory.
See [pytest-autocap-example](https://github.com/jwdevantier/pytest-autocap-example) if you want to try this out in practice, or want to read a detailed example.

Having all test output recorded automatically is helpful in case Pytest is driving long-running integration- or full-spectrum systems tests. Likewise, having a well-defined scheme for storing additional data generated as part of running these tests, can help splitting the test execution, which in case of systems tests may be significant, from subsequent analysis.

## How to use

### Installation
Install `pytest-autocap`:
```
pip install pytest-autocap
```

### Capture test output
... define some tests and add the `--autocap-dir` argument to pytest when running to capture output:
```
pytest --autocap-dir=/tmp/my-test-output -s .
```

Note, `-s` is equivalent to `--capture=no` and is required for autocap to capture test output. However, autocap will raise an error if you provide `--autocap-dir`, but fail to also set `-s`/`--capture=no`.

### Storing additional files in the test output directory
If a test generates additional data you wish to keep, use the `autocap_dir` fixture, which returns a `pathlib.Path` object. For example:

```python
def test_function_test(autocap_dir):
    with open(autocap_dir / "stuff.txt", "w") as fh:
        fh.write("hello, world\n")
    pass
```

## How it works
Autocap re-uses the capture fixture code which the various capture fixtures uses.

To capture output with plain Pytest, one of these capture fixtures (`capfd`, `capfdbinary`, `capsys`, `capsysbinary`) must be referenced in the argument list of a test function or function-scoped fixture.
However, these fixtures do not support capturing output for fixtures with a longer life-time, i.e. fixtures with `session`-, `module`- or `class`-wide scope.

To circumvent this requirement, and to track which fixture generates what output, autocap manually intializes capture fixtures using various pytest hooks and fixture finalizers.
All output is then stored until the test run is completed, at which point all fixtures have run their tear-down logic, and all output is finally written to the chosen output directory.
To see a detailed example, see [pytest-autocap-example](https://github.com/jwdevantier/pytest-autocap-example).

## Limitations
* You cannot mix autocap with the standard capture fixtures (`capfd`, `capfdbinary`, `capsys`, `capsysbinary`), or fixtures depending on those capture fixtures.
    * In case you do by mistake, pytest will exit with a helpful error message, pointing out which test or fixture caused the issue.
