# /// script
# dependencies = ["nox>=2025.02.09"]
# ///

from __future__ import annotations

import contextlib
import datetime
import difflib
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import IO, Generator

import nox

nox.needs_version = ">=2025.02.09"
nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv|virtualenv"

PYPROJECT = nox.project.load_toml("pyproject.toml")
PYTHON_VERSIONS = nox.project.python_versions(PYPROJECT)


@nox.session(
    python=[
        *PYTHON_VERSIONS,
        "pypy3.8",
        "pypy3.9",
        "pypy3.10",
        "pypy3.11",
    ],
    default=False,
)
def tests(session: nox.Session) -> None:
    coverage = ["python", "-m", "coverage"]

    session.install(*nox.project.dependency_groups(PYPROJECT, "test"))
    session.install("-e.")
    env = {} if session.python != "3.14" else {"COVERAGE_CORE": "sysmon"}

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


@nox.session(python="3.9")
def lint(session: nox.Session) -> None:
    # Run the linters (via pre-commit)
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files", *session.posargs)

    # Check the distribution
    session.install("build", "twine")
    session.run("pyproject-build")
    session.run("twine", "check", *glob.glob("dist/*"))


@nox.session(python="3.9", default=False)
def docs(session: nox.Session) -> None:
    shutil.rmtree("docs/_build", ignore_errors=True)
    session.install("-r", "docs/requirements.txt")
    session.install("-e", ".")

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
            "-b",
            builder,
            "-d",
            "docs/_build/doctrees/" + dest,
            "docs",  # source directory
            "docs/_build/" + dest,  # output directory
        )


@nox.session(default=False)
def release(session: nox.Session) -> None:
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

    major, minor = map(int, release_version.split("."))
    next_version = f"{major}.{minor + 1}.dev0"
    _bump(session, version=next_version, file=version_file, kind="development")

    # Push the commits and tag.
    # NOTE: The following fails if pushing to the branch is not allowed. This can
    #       happen on GitHub, if the main branch is protected, there are required
    #       CI checks and "Include administrators" is enabled on the protection.
    session.run("git", "push", "upstream", "main", release_version, external=True)


@nox.session
def release_build(session):
    # Parse version from command-line arguments, if provided, otherwise get
    # from Git tag.
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
        ["git", "status", "--porcelain"], capture_output=True, encoding="utf-8"
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


def _build_and_check(session, release_version, remove=False):
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


@nox.session(default=False)
def update_licenses(session: nox.Session) -> None:
    session.install("httpx")
    session.run("python", "tasks/licenses.py")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
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

    if not all(part.isdigit() for part in parts):
        # Not all segments are integers.
        raise ValueError("non-integer segments")

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
