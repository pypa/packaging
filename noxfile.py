# /// script
# dependencies = ["nox>=2025.02.09", "packaging"]
# ///

from __future__ import annotations

import contextlib
import datetime
import difflib
import glob
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
from pathlib import Path
from typing import IO, TYPE_CHECKING

import nox

import packaging.version  # will always be present with nox

if TYPE_CHECKING:
    from collections.abc import Generator

nox.needs_version = ">=2025.02.09"
nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv|virtualenv"

PYPROJECT = nox.project.load_toml("pyproject.toml")
PYTHON_VERSIONS = nox.project.python_versions(PYPROJECT)


@nox.session(
    python=[
        *PYTHON_VERSIONS,
        "3.13t",
        "3.14t",
        "3.15t",
        "pypy3.9",
        "pypy3.10",
        "pypy3.11",
    ],
    default=False,
)
def tests(session: nox.Session) -> None:
    """
    Run the tests, with coverage.
    """
    coverage = ["python", "-m", "coverage"]

    session.install(*nox.project.dependency_groups(PYPROJECT, "test"))
    session.install("-e.")
    env = {} if session.python != "3.14" else {"COVERAGE_CORE": "sysmon"}

    # Property tests are marked with @pytest.mark.property and are excluded by default
    # via pyproject.toml. Run the regular test suite normally; property tests can be
    # run explicitly with `pytest -m property` or the `property_tests` nox session.

    assert session.python is not None
    assert not isinstance(session.python, bool)
    if "pypy" not in session.python:
        session.run(
            *coverage,
            "run",
            "-m",
            "pytest",
            *session.posargs,
            env=env,
        )
        session.run(*coverage, "report")
    else:
        # Don't do coverage tracking for PyPy, since it's SLOW.
        session.run(
            "python",
            "-m",
            "pytest",
            "--capture=no",
            *session.posargs,
        )


@nox.session(default=False)
def property_tests(session: nox.Session) -> None:
    """
    Run property-based tests (no coverage).
    """
    session.install(*nox.project.dependency_groups(PYPROJECT, "test"))
    session.install("-e.")
    session.run(
        "python",
        "-m",
        "pytest",
        "-m",
        "property",
        *session.posargs,
    )


PROJECTS = {
    "packaging_legacy": "https://github.com/di/packaging_legacy/archive/refs/tags/23.0.post0.tar.gz",
    "build": "https://github.com/pypa/build/archive/refs/tags/1.5.0.tar.gz",
    "setuptools": "https://github.com/pypa/setuptools/archive/refs/tags/v82.0.0.tar.gz",
    "pyproject_metadata": "https://github.com/pypa/pyproject-metadata/archive/refs/tags/0.11.0.tar.gz",
    "pip": "https://github.com/pypa/pip/archive/refs/tags/26.0.1.tar.gz",
    "dependency_groups": "https://github.com/pypa/dependency-groups/archive/refs/tags/1.3.1.tar.gz",
    "dep_logic": "https://github.com/pdm-project/dep-logic/archive/refs/tags/0.6.0.tar.gz",
    "twine": "https://github.com/pypa/twine/archive/refs/tags/6.2.0.tar.gz",
    "cibuildwheel": "https://github.com/pypa/cibuildwheel/archive/refs/tags/v4.1.0.tar.gz",
    "hatchling": "https://github.com/pypa/hatch/archive/refs/tags/hatchling-v1.30.1.tar.gz",
    "tox": "https://github.com/tox-dev/tox/archive/refs/tags/4.55.1.tar.gz",
    "virtualenv": "https://github.com/pypa/virtualenv/archive/refs/tags/21.5.0.tar.gz",
    "pdm": "https://github.com/pdm-project/pdm/archive/refs/tags/2.27.0.tar.gz",
    "poetry_core": "https://github.com/python-poetry/poetry-core/archive/refs/tags/2.4.1.tar.gz",
    "pipenv": "https://github.com/pypa/pipenv/archive/refs/tags/v2026.6.2.tar.gz",
}

# The pinned releases below break under pytest 9.1.0 (released 2026-06-13), whose
# parametrize handling turns their test collection into errors. Rather than pin
# pytest by hand, cap dependency resolution at the day before it shipped, so they
# resolve pytest 9.0.x (and otherwise-current deps) on both the uv and pip
# backends. The newer downstream projects support 9.1.0 and are left alone.
PYTEST_910_CUTOFF = "2026-06-12"
DATE_LIMITED_PROJECTS = {
    "packaging_legacy",
    "build",
    "pyproject_metadata",
    "setuptools",
    "pip",
}


@nox.parametrize("project", list(PROJECTS))
@nox.session(default=False)
def downstream(session: nox.Session, project: str) -> None:
    """
    Run downstream projects with this packaging.
    """
    pkg_dir = Path.cwd() / "src/packaging"
    env = {"FORCE_COLOR": None}
    session.install("-e.")

    tmp_dir = Path(session.create_tmp())
    session.chdir(tmp_dir)

    shutil.rmtree(project, ignore_errors=True)
    with urllib.request.urlopen(PROJECTS[project]) as resp:
        data = resp.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(project)
    (inner_dir,) = Path(project).iterdir()
    session.chdir(inner_dir)

    pip_cmd = ["uv", "pip"] if session.venv_backend == "uv" else ["pip"]

    # nox points TMPDIR inside this git checkout, so downstream tools that walk
    # up the tree (hatchling's VCS sdist builder, tox/pdm config discovery) find
    # packaging's own repo metadata and misbehave. Run the newer projects' tests
    # with a temp dir outside the checkout. The original five do not need this.
    test_env = {**env, "TMPDIR": tempfile.mkdtemp(prefix="downstream-")}

    if project in DATE_LIMITED_PROJECTS:
        # See DATE_LIMITED_PROJECTS: cap resolution at the cutoff so these
        # projects pull a pytest they support, for both backends.
        session.env["UV_EXCLUDE_NEWER"] = PYTEST_910_CUTOFF
        session.env["PIP_UPLOADED_PRIOR_TO"] = PYTEST_910_CUTOFF

    if project == "packaging_legacy":
        session.install("-r", "tests/requirements.txt")
        session.install("-e.")
        session.run(*pip_cmd, "list")
        session.run("pytest", *session.posargs, env=env)
    elif project in {"build", "pyproject_metadata"}:
        session.install("-e.", "--group=test")
        if project != "build":
            session.run(*pip_cmd, "list")
        session.run("pytest", *session.posargs, env=env)
    elif project == "setuptools":
        session.install("-e.[test,cover]")
        session.run(*pip_cmd, "list")
        repl_dir = "setuptools/_vendor/packaging"
        shutil.rmtree(repl_dir)
        shutil.copytree(pkg_dir, repl_dir)
        skips = ["-k", "not test_editable_install and not test_editable_with_pyproject"]
        session.run("pytest", *skips, *session.posargs, env=env)
    elif project == "pip":
        session.install("-e.", "--group=test")
        session.run(
            "pip",
            "wheel",
            "-w",
            "tests/data/common_wheels",
            "--group",
            "test-common-wheels",
        )
        session.run(*pip_cmd, "list")
        repl_dir = "src/pip/_vendor/packaging"
        shutil.rmtree(repl_dir)
        shutil.copytree(pkg_dir, repl_dir)
        session.run(
            "pytest",
            "tests/unit",
            "--numprocesses=auto",
            "-k",
            "not test_ensure_svn_available",
            *session.posargs,
        )
    elif project == "dependency_groups":
        session.install("-e.", "--group=test")
        session.run(*pip_cmd, "list")
        session.run("pytest", *session.posargs, env=test_env)
    elif project == "dep_logic":
        # pdm-backend computes the version from git, absent in the tarball. Scope
        # the override to the build so it cannot leak into version-aware tests.
        session.install("-e.", "pytest", env={"PDM_BUILD_SCM_VERSION": "0.6.0"})
        session.run(*pip_cmd, "list")
        session.run("pytest", *session.posargs, env=test_env)
    elif project == "twine":
        # twine keeps its test deps in tox.ini rather than a [test] extra.
        session.install(
            "-e.",
            "pretend",
            "pytest",
            "pytest-socket",
            "coverage",
            env={"SETUPTOOLS_SCM_PRETEND_VERSION": "6.2.0"},
        )
        # test_fails_rst_syntax_error asserts an exact docutils warning string
        # that changed in newer docutils; unrelated to packaging.
        session.run(
            "pytest",
            "-k",
            "not test_fails_rst_syntax_error",
            *session.posargs,
            env=test_env,
        )
    elif project == "cibuildwheel":
        session.install("-e.", "--group=test")
        session.run(*pip_cmd, "list")
        # unit_test/ is the fast suite; test/ holds slow Docker integration tests.
        session.run("pytest", "unit_test", *session.posargs, env=test_env)
    elif project == "hatchling":
        # hatchling lives in the hatch monorepo; its backend tests under
        # tests/backend rely on the full hatch package and its fixtures. Keep the
        # version override out of the test env: hatchling has version-detection
        # tests that fail if SETUPTOOLS_SCM_PRETEND_VERSION is set while they run.
        session.install(
            "-e./backend",
            "-e.",
            "pytest",
            "pytest-mock",
            "filelock",
            "editables",
            env={"SETUPTOOLS_SCM_PRETEND_VERSION": "1.30.1"},
        )
        # test_binary downloads a PyApp binary over the network.
        session.run(
            "pytest",
            "tests/backend",
            "--ignore=tests/backend/builders/test_binary.py",
            *session.posargs,
            env=test_env,
        )
    elif project == "tox":
        # argcomplete is an optional dep that several tests import at collection.
        session.install(
            "-e.",
            "--group=test",
            "argcomplete",
            env={"SETUPTOOLS_SCM_PRETEND_VERSION": "4.55.1"},
        )
        # tox appends a pip-freeze line to command output when CI is set, which
        # several output-asserting tests do not expect, so run them without it.
        session.run(
            "pytest",
            "-m",
            "not integration",
            *session.posargs,
            env={**test_env, "CI": None},
        )
    elif project == "virtualenv":
        session.install(
            "-e.", "--group=test", env={"SETUPTOOLS_SCM_PRETEND_VERSION": "21.5.0"}
        )
        session.run("pytest", *session.posargs, env=test_env)
    elif project == "pdm":
        session.install("-e.", "--group=test", env={"PDM_BUILD_SCM_VERSION": "2.27.0"})
        session.run(
            "pytest",
            "-m",
            "not network and not integration",
            *session.posargs,
            env=test_env,
        )
    elif project == "poetry_core":
        # poetry-core uses poetry-native dependency groups, so its test deps are
        # not pip-installable as an extra; install them explicitly.
        session.install(
            "-e.",
            "pytest",
            "pytest-mock",
            "build",
            "setuptools",
            "tomli-w",
            "virtualenv",
            "trove-classifiers",
        )
        # poetry-core vendors packaging under _vendor and injects it onto
        # sys.path; replace it with the current source, as we do for pip.
        repl_dir = "src/poetry/core/_vendor/packaging"
        shutil.rmtree(repl_dir)
        shutil.copytree(pkg_dir, repl_dir)
        session.run("pytest", "tests", *session.posargs, env=test_env)
    elif project == "pipenv":
        session.install("-e.[tests]")
        # pipenv vendors packaging twice (its own vendor tree and the patched
        # pip); replace both with the current source.
        for repl_dir in (
            "pipenv/vendor/packaging",
            "pipenv/patched/pip/_vendor/packaging",
        ):
            shutil.rmtree(repl_dir)
            shutil.copytree(pkg_dir, repl_dir)
        # test_vendor.py asserts vendoring integrity (and needs pytz), so it is
        # expected to fail after the swap. pipenv's addopts enable --no-cov,
        # which errors without pytest-cov; replace them. integration tests need
        # the network.
        session.run(
            "pytest",
            "tests/unit",
            "--ignore=tests/unit/test_vendor.py",
            "-o",
            "addopts=-ra",
            *session.posargs,
            env=test_env,
        )
    else:
        session.error("Unknown package")


@nox.session(python="3.10")
def lint(session: nox.Session) -> None:
    """
    Run the linters.
    """
    session.install("prek", "build", "twine")

    # Run the linters (via prek, a Rust pre-commit runner)
    session.run("prek", "run", "--all-files", *session.posargs)

    # Check the distribution
    session.run("pyproject-build")
    session.run("twine", "check", *glob.glob("dist/*"))


@nox.session(default=False)
def docs(session: nox.Session) -> None:
    """
    Build the docs.
    """
    shutil.rmtree("docs/_build", ignore_errors=True)
    session.install(*nox.project.dependency_groups(PYPROJECT, "docs"))
    session.install("-e.")

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


@nox.session(default=False)
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


@nox.session
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
        session.run("git", "switch", "-q", release_version, external=True)

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
    session.install("httpx")
    session.run("python", "tasks/licenses.py")


@nox.session(default=False)
@nox.parametrize("version", ["21.0", "24.0", "25.0", "26.0", "26.1"])
def test_pickle(session: nox.Session, version: str) -> None:
    """
    Make sure pickles written by an older packaging release can be read
    by the current code.
    """
    tmp_dir = Path(session.create_tmp())
    pickle_file = tmp_dir / f"packaging_{version}_pickles.pkl"

    # Step 1: install the old release so the generator pickles objects in
    # the format that version serialises.
    session.install(f"packaging=={version}")
    session.run(
        "python",
        "tasks/pickle_compat.py",
        "write",
        version,
        str(tmp_dir),
    )

    # Step 2: install the current (in-tree) packaging so we can verify
    # backward compatibility of the load path.
    session.install("-e.")
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

    session.install("build", "twine")

    # Determine if we're in install-only mode. This works as `python --version`
    # should always succeed when running `nox`, but in install-only mode
    # `session.run(..., silent=True)` always immediately returns `None` instead
    # of invoking the command and returning the command's output. See the
    # documentation at:
    # https://nox.thea.codes/en/stable/usage.html#skipping-everything-but-install-commands
    install_only = session.run("python", "--version", silent=True) is None

    # Build the distribution.
    session.run("python", "-m", "build")

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
) -> Generator[tuple[IO[str], IO[str]], None, None]:
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
