# /// script
# dependencies = ["nox>=2025.02.09", "packaging"]
# ///

from __future__ import annotations

import argparse
import contextlib
import datetime
import difflib
import glob
import hashlib
import importlib.metadata
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING

import nox

import packaging.version  # will always be present with nox

if TYPE_CHECKING:
    from collections.abc import Generator

nox.needs_version = ">=2025.02.09"
nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv|virtualenv"

# Parallel mode added in modern nox
NOX_VERSION = packaging.version.Version(importlib.metadata.version("nox"))
if packaging.version.Version("2026.08.10") <= NOX_VERSION:
    nox.options.allow_parallel = True

ROOT = Path(__file__).resolve().parent
PYPROJECT = nox.project.load_toml(ROOT / "pyproject.toml")
PYTHON_VERSIONS = nox.project.python_versions(PYPROJECT)
DOWNSTREAM = ROOT / "tasks" / "downstream"
DOWNSTREAM_CONFIG = nox.project.load_toml(DOWNSTREAM / "nab.toml")
DEV_LOCK = ROOT / "pylock.dev.toml"
BUILD_LOCK = ROOT / "pylock.build.toml"
PYTEST_91_UPLOAD_CUTOFF = "2026-06-12 00:00:00Z"

# Interpreters that run the tests without coverage, because tracing is too slow
# there: PyPy, and free-threaded 3.13, which has no fast C tracer.
NO_COVERAGE = {"pypy", "3.13t"}


def _install_group(session: nox.Session, group: str) -> None:
    """Select a development-lock group using the session's installer."""
    if session.venv_backend == "uv":
        session.install("-r", str(DEV_LOCK), "--group", group)
    else:
        session.install("--group", f"{DEV_LOCK}:{group}")


def _install_project(session: nox.Session, *, editable: bool = True) -> None:
    """Build the current source using the already installed locked backend."""
    session.install("--no-deps", "--no-build-isolation", "-e." if editable else ".")


@nox.session(
    python=[
        *PYTHON_VERSIONS,
        "3.13t",
        "3.14t",
        "3.15t",
        "pypy3.10",
        "pypy3.11",
    ],
    default=False,
)
def tests(session: nox.Session) -> None:
    """
    Run the tests, with coverage.
    """
    assert session.python is not None
    assert not isinstance(session.python, bool)

    parser = argparse.ArgumentParser(prog="nox -s tests --")
    parser.add_argument(
        "--coverage",
        action=argparse.BooleanOptionalAction,
        default=not any(x in session.python for x in NO_COVERAGE),
        help="Run the tests under coverage.",
    )
    args, posargs = parser.parse_known_args(session.posargs)

    coverage = ["python", "-m", "coverage"]

    _install_group(session, "test")
    _install_project(session)

    # Give each session its own data file so parallel sessions don't fight over
    # the default ".coverage".
    env = {"COVERAGE_FILE": str(Path.cwd() / f".coverage.{session.python}")}
    if session.python == "3.14":
        env["COVERAGE_CORE"] = "sysmon"

    # Property tests are marked with @pytest.mark.property and are excluded by default
    # via pyproject.toml. Run the regular test suite normally; property tests can be
    # run explicitly with `pytest -m property` or the `property_tests` nox session.

    if args.coverage:
        session.run(
            *coverage,
            "run",
            "-m",
            "pytest",
            *posargs,
            env=env,
        )
        session.run(*coverage, "report", env=env)
    else:
        session.run(
            "python",
            "-m",
            "pytest",
            "--capture=no",
            *posargs,
        )


@nox.session(default=False)
def property_tests(session: nox.Session) -> None:
    """
    Run property-based tests (no coverage).
    """
    _install_group(session, "test")
    _install_project(session)
    session.run(
        "python",
        "-m",
        "pytest",
        "-m",
        "property",
        *session.posargs,
    )


@nox.session(python="3.14", default=False)
def locks(session: nox.Session) -> None:
    """Check or refresh all dependency locks with the committed locker toolchain."""
    _install_group(session, "locks")
    # Expose the groups included by dev for individual CI sessions.
    groups = [
        entry["include-group"]
        for entry in PYPROJECT["dependency-groups"]["dev"]
        if isinstance(entry, dict)
    ]
    session.run(
        "nab",
        "lock",
        "--output",
        DEV_LOCK.name,
        "--groups",
        "dev",
        *groups,
        *session.posargs,
    )
    session.run("nab", "lock", "--all-plans", *session.posargs)
    session.run(
        "nab",
        "lock",
        "tasks/downstream/nab.toml",
        "--all-plans",
        *session.posargs,
    )


@dataclass(frozen=True)
class Project:
    install_env: dict[str, str] | None = None
    swap: tuple[str, ...] = ()
    pytest_args: tuple[str, ...] = ()
    extra_env: dict[str, str | None] | None = None
    pytest_before_9_1: bool = False
    uninstall_after_build: tuple[str, ...] = ()
    isolated_home: bool = False


PROJECTS = {
    "packaging_legacy": Project(
        pytest_before_9_1=True,
    ),
    "build": Project(
        # Exercise metadata extraction with its backend absent, as the suite expects.
        uninstall_after_build=("flit-core",),
    ),
    "setuptools": Project(
        swap=("setuptools/_vendor/packaging",),
        pytest_args=(
            # Performance comparisons require a Git checkout.
            "-p",
            "no:perf",
            "-k",
            "not test_editable_install and not test_editable_with_pyproject",
        ),
        pytest_before_9_1=True,
    ),
    "pyproject_metadata": Project(
        pytest_before_9_1=True,
    ),
    "pip": Project(
        swap=("src/pip/_vendor/packaging",),
        pytest_args=(
            "tests/unit",
            "--numprocesses=auto",
            "-k",
            "not test_ensure_svn_available",
        ),
        pytest_before_9_1=True,
    ),
    "dependency_groups": Project(),
    "dep_logic": Project(
        install_env={"PDM_BUILD_SCM_VERSION": "0.6.0"},
    ),
    "twine": Project(
        install_env={"SETUPTOOLS_SCM_PRETEND_VERSION": "7.0.0"},
        isolated_home=True,
        extra_env={
            "TWINE_PASSWORD": None,
            "TWINE_USERNAME": None,
            "TWINE_CONFIG_FILE": None,
            "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        },
        # test_fails_rst_no_content expects an RST document with only a title
        # to render as empty, which readme_renderer 46 changed; unrelated to
        # packaging.
        pytest_args=("-k", "not test_fails_rst_no_content"),
    ),
    "cibuildwheel": Project(
        # unit_test/ is the fast suite; test/ holds slow Docker integration tests.
        pytest_args=("unit_test",),
    ),
    "hatchling": Project(
        # hatchling lives in the hatch monorepo; its backend tests rely on the
        # full hatch package and its fixtures.
        install_env={"SETUPTOOLS_SCM_PRETEND_VERSION": "1.31.0"},
        # test_binary downloads a PyApp binary over the network.
        # See https://github.com/pypa/hatch/issues/2319.
        # hatchling ships no pytest config, so from nox's tmp dir inside this
        # checkout pytest makes packaging's own directory the rootdir. Node IDs
        # then carry a .nox/... prefix, which silently breaks --deselect.
        pytest_args=(
            "tests/backend",
            "--rootdir=.",
            "--ignore=tests/backend/builders/test_binary.py",
        ),
    ),
    "tox": Project(
        install_env={"SETUPTOOLS_SCM_PRETEND_VERSION": "4.67.9"},
        # packaging rejects the test's newline URL before tox's validation runs.
        pytest_args=(
            "-m",
            "not integration",
            "--deselect=tests/tox_env/python/pip/test_req_file.py::"
            "test_provision_requirement_entry_cannot_change_lines[line-break]",
        ),
        # In CI, tox appends a pip-freeze line to command output, which several
        # output-asserting tests do not expect. Unset every variable its is_ci()
        # (tox/util/ci.py) checks that GitHub Actions sets.
        extra_env={"CI": None, "GITHUB_ACTIONS": None},
    ),
    "virtualenv": Project(
        install_env={"SETUPTOOLS_SCM_PRETEND_VERSION": "21.15.5"},
    ),
    "pdm": Project(
        install_env={"PDM_BUILD_SCM_VERSION": "2.29.7"},
        uninstall_after_build=("pdm-backend", "pdm-build-locked"),
        pytest_args=("-m", "not network and not integration"),
    ),
    "poetry_core": Project(
        # poetry-core vendors packaging under _vendor and injects it onto sys.path.
        swap=("src/poetry/core/_vendor/packaging",),
        pytest_args=("tests",),
    ),
    "pipenv": Project(
        # pipenv vendors packaging twice: its own vendor tree and the patched pip.
        swap=("pipenv/vendor/packaging", "pipenv/patched/pip/_vendor/packaging"),
        # test_vendor.py asserts vendoring integrity (and needs pytz), so it is
        # expected to fail after the swap. pipenv's addopts enable --no-cov, which
        # errors without pytest-cov; replace them.
        pytest_args=(
            "tests/unit",
            "--ignore=tests/unit/test_vendor.py",
            "-o",
            "addopts=-ra",
        ),
    ),
}


def download_project(source_name: str) -> bytes:
    """Download and verify the source that supplied the locked requirements."""
    source = DOWNSTREAM_CONFIG["input-sources"][source_name]
    with urllib.request.urlopen(source["url"]) as response:
        data = response.read()
    if not isinstance(data, bytes):
        raise TypeError("expected source archive bytes")
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ValueError("downstream archive differs from its pinned dependency input")
    return data


def _editable_sources(name: str) -> list[str]:
    """Read the editable projects and extras selected from the pinned source."""
    selection = DOWNSTREAM_CONFIG["plans"][name]["inputs"][name]
    result = []
    for item in selection.get("projects", [selection]):
        extras = item.get("extras", [])
        suffix = "[" + ",".join(extras) + "]" if extras else ""
        result.append("-e" + item.get("path", ".") + suffix)
    return result


def _prepare_downstream(session: nox.Session, project: str) -> None:
    """Enter the verified source tree without inheriting pytest configuration."""
    tmp_dir = Path(session.create_tmp())
    session.chdir(tmp_dir)

    shutil.rmtree(project, ignore_errors=True)
    data = download_project(project)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(project, filter="data")
    project_path = Path(project)
    (inner_dir,) = project_path.iterdir()
    # Make sure pytest doesn't keep searching upwards for config
    project_path.joinpath("pytest.ini").touch()
    session.chdir(inner_dir)


def _install_downstream(session: nox.Session, project: str, cfg: Project) -> None:
    """Install source and fixture wheels without resolving their dependencies again."""
    if project == "pip":
        # Build these before installing the older pip that is under test.
        session.run_install(
            "python",
            "-m",
            "pip",
            "wheel",
            "-w",
            "tests/data/common_wheels",
            "-r",
            str(DOWNSTREAM / "pylock.pip-wheels.toml"),
        )

    session.install(
        "--no-deps",
        "--no-build-isolation",
        *_editable_sources(project.replace("_", "-")),
        env=cfg.install_env,
    )
    if cfg.uninstall_after_build:
        session.run_install(
            "python", "-m", "pip", "uninstall", "--yes", *cfg.uninstall_after_build
        )
    session.run("python", "-m", "pip", "check")


@nox.parametrize("project", list(PROJECTS))
@nox.session(python="3.14", default=False)
def downstream(session: nox.Session, project: str) -> None:
    """Run downstream projects with the current packaging wheel and vendored sources."""
    cfg = PROJECTS[project]
    name = project.replace("_", "-")
    session.install("-r", str(DOWNSTREAM / f"pylock.{name}.toml"))
    # virtualenv's relocation tests copy the files listed in packaging's RECORD.
    _install_project(session, editable=False)
    _prepare_downstream(session, name)

    # Keep test-created projects outside this checkout's VCS and tool configuration.
    with tempfile.TemporaryDirectory(prefix="downstream-") as test_tmp:
        test_env: dict[str, str | None] = {
            "FORCE_COLOR": None,
            "NO_COLOR": None,
            "TMPDIR": test_tmp,
        }
        if cfg.isolated_home:
            # Match the downstream suite's clean home without reading host credentials.
            home = Path(test_tmp) / "home"
            home.mkdir()
            test_env["HOME"] = str(home)
        if cfg.pytest_before_9_1:
            # Preserve the cutoff for installers started by these legacy tests.
            test_env["UV_EXCLUDE_NEWER"] = PYTEST_91_UPLOAD_CUTOFF
            test_env["PIP_UPLOADED_PRIOR_TO"] = PYTEST_91_UPLOAD_CUTOFF
        if cfg.extra_env is not None:
            test_env |= cfg.extra_env

        _install_downstream(session, project, cfg)
        for repl_dir in cfg.swap:
            # Relative imports keep the replacement self-contained when vendored.
            shutil.rmtree(repl_dir)
            shutil.copytree(ROOT / "src/packaging", repl_dir)

        session.run("python", "-m", "pip", "list")
        session.run("pytest", *cfg.pytest_args, *session.posargs, env=test_env)


@nox.session(python="3.10")
def lint(session: nox.Session) -> None:
    """
    Run the linters.
    """
    _install_group(session, "lint")

    # Run the linters (via prek, a Rust pre-commit runner)
    session.run("prek", "run", "--all-files", *session.posargs)

    # Check the distribution. Build into the session temp dir, so this does not
    # collide with the "dist/" the release sessions manage.
    out_dir = Path(session.create_tmp()) / "dist"
    session.run("pyproject-build", "--no-isolation", "--outdir", str(out_dir))
    session.run("twine", "check", *glob.glob(f"{out_dir}/*"))


@nox.session(default=False)
def docs(session: nox.Session) -> None:
    """
    Build the docs.
    """
    shutil.rmtree("docs/_build", ignore_errors=True)
    _install_group(session, "docs")
    _install_project(session)

    variants = [
        # (builder, dest)
        ("html", "html"),
        ("latex", "latex"),
        ("doctest", "html"),
    ]

    for builder, dest in variants:
        session.run(
            "sphinx-build",
            "-W",
            "-n",
            "-b",
            builder,
            "-d",
            "docs/_build/doctrees/" + dest,
            "docs",  # source directory
            "docs/_build/" + dest,  # output directory
        )

    session.log(
        "Finished! If you want to view at http://localhost:8000, try:\n"
        "      python3 -m http.server -d docs/_build/html/"
    )


@nox.session(python="3.14", default=False)
def release(session: nox.Session) -> None:
    """
    Give a version number to use as tag.
    """
    package_name = "packaging"
    version_file = Path(f"src/{package_name}/__init__.py")
    changelog_file = Path("CHANGELOG.rst")

    try:
        release_version = _get_version_from_arguments(session.posargs)
    except ValueError as e:
        session.error(f"Invalid arguments: {e}")
        return

    # Check state of working directory and git.
    _check_working_directory_state(session)
    _check_git_state(session, release_version)

    # Prepare for release.
    _changelog_update_unreleased_title(release_version, file=changelog_file)
    session.run("git", "add", str(changelog_file), external=True)
    _bump(session, version=release_version, file=version_file, kind="release")

    # Check the built distribution.
    _build_and_check(session, release_version, remove=True)

    # Tag the release commit.
    # fmt: off
    session.run(
        "git", "tag",
        "-s", release_version,
        "-m", f"Release {release_version}",
        external=True,
    )
    # fmt: on
    release_sha = session.run(
        "git",
        "rev-parse",
        f"{release_version}^{{commit}}",
        silent=True,
        external=True,
    )
    release_sha = "" if release_sha is None else release_sha.strip()

    # Prepare for development.
    _changelog_add_unreleased_title(file=changelog_file)
    session.run("git", "add", str(changelog_file), external=True)

    rel_ver = packaging.version.Version(release_version)
    next_version = f"{rel_ver.major}.{rel_ver.minor + 1}.dev0"
    _bump(session, version=next_version, file=version_file, kind="development")

    # Push the commits and tag.
    # NOTE: The following fails if pushing to the branch is not allowed. This can
    #       happen on GitHub, if the main branch is protected, there are required
    #       CI checks and "Include administrators" is enabled on the protection.
    session.log("Run the following to push changes and tag (assuming 'upstream')")
    print()
    print(f"  git push upstream main {release_version}")
    print()
    session.log("Then trigger the publish workflow with this release commit SHA:")
    print()
    print(f"  {release_sha}")
    print()


@nox.session(python="3.14", default=False)
def release_build(session: nox.Session) -> None:
    """
    Build version from command-line arguments otherwise current Git tag.
    """
    release_version: str | None
    try:
        release_version = _get_version_from_arguments(session.posargs)
    except ValueError as e:
        if session.posargs:
            session.error(f"Invalid arguments: {e}")

        release_version = session.run(
            "git", "describe", "--exact-match", silent=True, external=True
        )
        release_version = "" if release_version is None else release_version.strip()
        session.debug(f"version: {release_version}")
        checkout = False
    else:
        checkout = True

    # Check state of working directory.
    _check_working_directory_state(session)

    # Ensure there are no uncommitted changes.
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        capture_output=True,
        encoding="utf-8",
    )
    if result.stdout:
        print(result.stdout, end="", file=sys.stderr)
        session.error("The working tree has uncommitted changes")

    # Check out the Git tag, if provided.
    if checkout:
        session.run("git", "switch", "--detach", "-q", release_version, external=True)

    # Build the distribution.
    _build_and_check(session, release_version)

    # Get back out into main, if we checked out before.
    if checkout:
        session.run("git", "switch", "-q", "main", external=True)


@nox.session(default=False)
def update_licenses(session: nox.Session) -> None:
    """
    Update licenses.
    """
    _install_group(session, "licenses")
    session.run("python", "tasks/licenses.py")


@nox.session(default=False)
@nox.parametrize("version", ["21.0", "24.0", "25.0", "26.0", "26.1", "26.2", "26.3"])
def test_pickle(session: nox.Session, version: str) -> None:
    """
    Make sure pickles written by an older packaging release can be read
    by the current code.
    """
    tmp_dir = Path(session.create_tmp())
    pickle_file = tmp_dir / f"packaging_{version}_pickles.pkl"

    # Step 1: install the old release so the generator pickles objects in
    # the format that version serialises.
    lock = ROOT / "tasks" / "pickle" / f"pylock.pickle-{version.replace('.', '-')}.toml"
    session.install("-r", str(lock))
    session.run(
        "python",
        "tasks/pickle_compat.py",
        "write",
        version,
        str(tmp_dir),
    )

    # Step 2: install the current (in-tree) packaging so we can verify
    # backward compatibility of the load path.
    _install_project(session)
    session.run(
        "python",
        "tasks/pickle_compat.py",
        "verify",
        "--version",
        version,
        str(pickle_file),
    )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _build_and_check(
    session: nox.Session,
    release_version: str,
    remove: bool = False,
) -> None:
    package_name = "packaging"

    session.install("-r", str(BUILD_LOCK))

    # Determine if we're in install-only mode. This works as `python --version`
    # should always succeed when running `nox`, but in install-only mode
    # `session.run(..., silent=True)` always immediately returns `None` instead
    # of invoking the command and returning the command's output. See the
    # documentation at:
    # https://nox.thea.codes/en/stable/usage.html#skipping-everything-but-install-commands
    install_only = session.run("python", "--version", silent=True) is None

    # Build the distribution.
    session.run("python", "-m", "build", "--no-isolation")

    # Check what files are in dist/ for upload.
    files = sorted(glob.glob("dist/*"))
    expected = [
        f"dist/{package_name}-{release_version}-py3-none-any.whl",
        f"dist/{package_name}-{release_version}.tar.gz",
    ]
    if files != expected and not install_only:
        diff_generator = difflib.context_diff(
            expected, files, fromfile="expected", tofile="got", lineterm=""
        )
        diff = "\n".join(diff_generator)
        session.error(f"Got the wrong files:\n{diff}")

    # Check distribution files.
    session.run("twine", "check", "--strict", *files)

    # Remove distribution files, if requested.
    if remove and not install_only:
        shutil.rmtree("dist", ignore_errors=True)


def _get_version_from_arguments(arguments: list[str]) -> str:
    """Checks the arguments passed to `nox -s release`.

    Only 1 argument that looks like a version? Return the argument.
    Otherwise, raise a ValueError describing what's wrong.
    """
    if len(arguments) != 1:
        raise ValueError("Expected exactly 1 argument")

    version = arguments[0]
    parts = version.split(".")

    if len(parts) != 2:
        # Not of the form: YY.N
        raise ValueError("not of the form: YY.N")

    norm_version = str(packaging.version.Version(version))
    if norm_version != version:
        raise ValueError(f"Must be normalized version {norm_version!r}")

    # All is good.
    return version


def _check_working_directory_state(session: nox.Session) -> None:
    """Check state of the working directory, prior to making the release."""
    should_not_exist = ["build/", "dist/"]

    bad_existing_paths = list(filter(os.path.exists, should_not_exist))
    if bad_existing_paths:
        session.error(f"Remove {', '.join(bad_existing_paths)} and try again")


def _check_git_state(session: nox.Session, version_tag: str) -> None:
    """Check state of the git repository, prior to making the release."""
    # Ensure the upstream remote pushes to the correct URL.
    allowed_upstreams = [
        "git@github.com:pypa/packaging.git",
        "https://github.com/pypa/packaging.git",
    ]
    result = subprocess.run(
        ["git", "remote", "get-url", "--push", "upstream"],
        check=False,
        capture_output=True,
        encoding="utf-8",
    )
    if result.stdout.rstrip() not in allowed_upstreams:
        session.error(f"git remote `upstream` is not one of {allowed_upstreams}")
    # Ensure we're on main branch for cutting a release.
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        check=False,
        capture_output=True,
        encoding="utf-8",
    )
    if result.stdout != "main\n":
        session.error(f"Not on main branch: {result.stdout!r}")

    # Ensure there are no uncommitted changes.
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        capture_output=True,
        encoding="utf-8",
    )
    if result.stdout:
        print(result.stdout, end="", file=sys.stderr)
        session.error("The working tree has uncommitted changes")

    # Ensure this tag doesn't exist already.
    result = subprocess.run(
        ["git", "rev-parse", version_tag],
        check=False,
        capture_output=True,
        encoding="utf-8",
    )
    if not result.returncode:
        session.error(f"Tag already exists! {version_tag} -- {result.stdout!r}")

    # Back up the current git reference, in a tag that's easy to clean up.
    _release_backup_tag = "auto/release-start-" + str(int(time.time()))
    session.run("git", "tag", _release_backup_tag, external=True)


def _bump(session: nox.Session, *, version: str, file: Path, kind: str) -> None:
    session.log(f"Bump version to {version!r}")
    contents = file.read_text()
    new_contents = re.sub(
        '__version__ = "(.+)"', f'__version__ = "{version}"', contents
    )
    file.write_text(new_contents)

    session.log("git commit")
    subprocess.run(["git", "add", str(file)], check=False)
    subprocess.run(["git", "commit", "-m", f"Bump for {kind}"], check=False)


@contextlib.contextmanager
def _replace_file(
    original_path: Path,
) -> Generator[tuple[IO[str], IO[str]]]:
    # Create a temporary file.
    fh, replacement_path = tempfile.mkstemp()

    with os.fdopen(fh, "w") as replacement, open(original_path) as original:
        yield original, replacement

    shutil.copymode(original_path, replacement_path)
    os.remove(original_path)
    shutil.move(replacement_path, original_path)


def _changelog_update_unreleased_title(version: str, *, file: Path) -> None:
    """Update an "*unreleased*" heading to "{version} - {date}" """
    yyyy_mm_dd = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d")
    title = f"{version} - {yyyy_mm_dd}"

    with _replace_file(file) as (original, replacement):
        for line in original:
            if line == "*unreleased*\n":
                replacement.write(f"{title}\n")
                replacement.write(len(title) * "~" + "\n")
                # Skip processing the next line (the heading underline for *unreleased*)
                # since we already wrote the heading underline.
                next(original)
            else:
                replacement.write(line)


def _changelog_add_unreleased_title(*, file: Path) -> None:
    with _replace_file(file) as (original, replacement):
        # Duplicate first 3 lines from the original file.
        for _ in range(3):
            line = next(original)
            replacement.write(line)

        # Write the heading.
        replacement.write(
            textwrap.dedent(
                """\
                *unreleased*
                ~~~~~~~~~~~~

                No unreleased changes.

                """
            )
        )

        # Duplicate all the remaining lines.
        for line in original:
            replacement.write(line)


if __name__ == "__main__":
    nox.main()
