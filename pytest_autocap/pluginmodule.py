from pathlib import Path
from typing import Optional, Tuple

import pytest
from _pytest.capture import CaptureFixture, FDCaptureBinary
from pytest import Config


OPT_BASEDIR_ARGNAME = "autocap-dir"
OPT_BASEDIR_DEST = "AUTOCAP_BASEDIR"
STASH_FIXTURE_LOGS = "pytest-autocap::fixtures::logs"
STASH_TEST_LOGS = "pytest-autocap::tests::logs"

CAPTURE_FIXTURES = {"capfd", "capfdbinary", "capsys", "capsysbinary"}


def _utf8str(s: bytes):
    return str(s, encoding="utf-8", errors="substitute")


def _autocap_basedir(config: Config) -> Optional[Path]:
    val = config.getoption(OPT_BASEDIR_DEST, None)
    return Path(val) if val else None


def _autocap_enabled(config: Config) -> bool:
    return config.getoption(OPT_BASEDIR_DEST, None) is not None


def pytest_addoption(parser):
    group = parser.getgroup("autocap", "autocap plugin")
    group.addoption(
        f"--{OPT_BASEDIR_ARGNAME}",
        action="store",
        default=None,
        help="enable autocap and write results to given directory",
        dest=OPT_BASEDIR_DEST,
    )


def _nodeid_to_autocap_dir(config: Config, nodeid: str) -> Optional[Path]:
    basedir = _autocap_basedir(config)
    assert basedir is not None, "expected a basedir - but none has been set"
    if basedir is None:
        return None

    parts = nodeid.split("::")
    module_relpath = Path(parts[0])
    module_relpath = (
        module_relpath.parent / module_relpath.name[: -len(module_relpath.suffix)]
    )
    parts[0] = str(basedir / module_relpath)
    return Path(*parts)


@pytest.fixture(scope="session")
def autocap_basedir(pytestconfig) -> Optional[Path]:
    bdir = _autocap_basedir(pytestconfig)
    if bdir and not bdir.is_dir():
        bdir.mkdir(parents=True)
    return bdir


@pytest.fixture()
def autocap_dir(request, pytestconfig) -> Optional[Path]:
    if _autocap_basedir(pytestconfig) is None:
        return None
    dpath = _nodeid_to_autocap_dir(pytestconfig, request.node.nodeid)
    if not dpath.is_dir():
        dpath.mkdir(parents=True)
    return dpath


class FixtureLog:
    def __init__(self, fixture: str, before: CaptureFixture, after: CaptureFixture):
        self._fixture = fixture
        self._before = before
        self._bouterr = None
        self._after = after
        self._aouterr = None
        self.__closed = False

    @property
    def fixture(self) -> str:
        return self._fixture

    def before_outerr(self) -> Tuple[str, str]:
        if self._bouterr is None:
            out, err = self._before.readouterr()
            self._bouterr = _utf8str(out), _utf8str(err)
        return self._bouterr

    def after_outerr(self) -> Tuple[str, str]:
        if self._aouterr is None:
            out, err = self._after.readouterr()
            self._aouterr = _utf8str(out), _utf8str(err)
        return self._aouterr

    def __eq__(self, other):
        return self._fixture == other._fixture

    def __hash__(self):
        return hash(self._fixture)

    def close(self):
        if self.__closed:
            return
        self.before_outerr()
        self.after_outerr()
        self._before.close()
        self._after.close()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_fixture_setup(fixturedef, request):
    config = fixturedef._fixturemanager.config
    fixture_name = fixturedef.argname
    capman = config.pluginmanager.getplugin("capturemanager")

    if CAPTURE_FIXTURES.intersection(fixturedef.argnames):
        raise pytest.UsageError(
            f"cannot use capture fixtures ({CAPTURE_FIXTURES}) when using autocap"
        )

    def _create_capture_fixture():
        return pytest.CaptureFixture[bytes](
            FDCaptureBinary, request=request, _ispytest=True
        )

    cf_before = _create_capture_fixture()
    cf_after = _create_capture_fixture()
    flog = FixtureLog(fixture_name, cf_before, cf_after)
    config.stash[STASH_FIXTURE_LOGS][fixture_name] = flog

    capman.set_fixture(cf_before)
    try:
        cf_before._start()
        try:
            yield
            flog.before_outerr()  # run for side-effects, capture output
        finally:
            cf_before.close()
    finally:
        capman.unset_fixture()

    # yield fixtures are equivalent to fixtures explicitly adding
    # a finalizer function for cleanup-purposes.
    # Since this hook runs ahead of fixture execution (and before other hooks)
    # our finalizer gets to be first.
    # This finalizer creates a new capture object and captures the output generated
    # by the teardown steps.
    def _on_teardown_start():
        capman.set_fixture(cf_after)
        cf_after._start()

    request.addfinalizer(_on_teardown_start)


@pytest.hookimpl(tryfirst=True)
def pytest_fixture_post_finalizer(fixturedef, request):
    fixture_name = fixturedef.argname
    config = fixturedef._fixturemanager.config
    flog: Optional[FixtureLog] = config.stash[STASH_FIXTURE_LOGS].get(fixture_name)

    # skip in case initialization in `pytest_fixture_setup` failed.
    if flog is None:
        return

    # The capture fixture created by the our fixture finalizer should be
    # turned off and removed again such that other fixtures may install their
    # own capture objects.

    capman = config.pluginmanager.getplugin("capturemanager")

    try:
        flog.after_outerr()  # run for side-effects, capture output
    finally:
        flog._after.close()
        capman.unset_fixture()


class StubRequest:
    def __init__(self, fixturename: str):
        self.fixturename = fixturename


@pytest.hookimpl()
def pytest_runtest_setup(item):
    if CAPTURE_FIXTURES.intersection(item.fixturenames):
        raise pytest.UsageError(
            f"cannot use capture fixtures ({CAPTURE_FIXTURES}) when using autocap"
        )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_call(item):
    if not _autocap_enabled(item.config):
        yield
        return
    # nodeid already of form:
    # <test-module-relpath>[::<test class>]::[testname]
    # (with parametrization etc supported.)
    config = item.config
    autocap_dir = _nodeid_to_autocap_dir(config, item.nodeid)
    assert isinstance(autocap_dir, Path), "expected a autocap_dir"
    capman = config.pluginmanager.getplugin("capturemanager")
    flogs = [
        flog
        for flog in (
            config.stash[STASH_FIXTURE_LOGS].get(fixture_name, None)
            for fixture_name in item.fixturenames
        )
        if flog is not None
    ]

    cf = pytest.CaptureFixture[bytes](
        FDCaptureBinary, request=StubRequest(item.nodeid), _ispytest=True
    )

    capman.set_fixture(cf)
    try:
        cf._start()
        try:
            yield
        finally:
            cf_out, cf_err = cf.readouterr()
            cf.close()
    finally:
        capman.unset_fixture()

    config.stash[STASH_TEST_LOGS].append(
        (
            autocap_dir,
            _utf8str(cf_out),
            _utf8str(cf_err),
            flogs,
        )
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    config.stash[STASH_FIXTURE_LOGS] = {}
    config.stash[STASH_TEST_LOGS] = []

    record = config.getoption(OPT_BASEDIR_DEST)
    if not record:
        return

    # TODO: plugins can use `pytest_load_initial_conftests`
    capture = config.getoption("capture")
    if not capture == "no":
        pytest.exit(f"if --{OPT_BASEDIR_ARGNAME} is set, --capture=no/-s")

    record = Path(record)
    if record.exists():
        if not record.is_dir():
            pytest.exit(f"{OPT_BASEDIR_ARGNAME!r} argument must not point to a file")
        elif any(record.iterdir()):
            pytest.exit(
                f"{OPT_BASEDIR_ARGNAME!r} argument must not point to an existing, non-empty directory"
            )
    else:
        record.mkdir()


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    def _write_section(fixturename, fh, out, err):
        if out:
            fh.write(f"=== {fixturename} - stdout:\n")
            fh.write(out)
            fh.write("\n")
        if err:
            fh.write(f"=== {fixturename} - stderr:\n")
            fh.write(err)
            fh.write("\n")
        if not out and not err:
            fh.write(f"=== {fixturename} - no output\n")

    for tst_path, tst_out, tst_err, flogs in config.stash[STASH_TEST_LOGS]:
        if not tst_path.is_dir():
            tst_path.mkdir(parents=True)

        with open(tst_path / "log.setup.txt", "w") as fh:
            for flog in flogs:
                out, err = flog.before_outerr()
                _write_section(flog.fixture, fh, out, err)

        with open(tst_path / "log.test.txt", "w") as fh:
            fh.write(tst_out)
            fh.write("\n")
            fh.write(tst_err)

        with open(tst_path / "log.teardown.txt", "w") as fh:
            flogs_reverse = list(flogs)
            flogs_reverse.reverse()
            for flog in flogs_reverse:
                out, err = flog.after_outerr()
                _write_section(flog.fixture, fh, out, err)
