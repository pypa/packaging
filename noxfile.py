# mypy: disallow-untyped-defs=False, disallow-untyped-calls=False

import time
import re
import os
import glob
import shutil
import subprocess
from pathlib import Path

import nox

nox.options.sessions = ["lint"]
nox.options.reuse_existing_virtualenvs = True


@nox.session(python=["2.7", "3.4", "3.5", "3.6", "3.7", "3.8", "pypy", "pypy3"])
def tests(session):
    def coverage(*args):
        session.run("python", "-m", "coverage", *args)

    session.install("coverage<5.0.0", "pretend", "pytest", "pip>=9.0.2")

    if "pypy" not in session.python:
        coverage("run", "--source", "packaging/", "-m", "pytest", "--strict")
        coverage("report", "-m", "--fail-under", "100")
    else:
        # Don't do coverage tracking for PyPy, since it's SLOW.
        session.run("pytest", "--capture=no", "--strict", *session.posargs)


@nox.session(python="3.8")
def lint(session):
    # Run the linters (via pre-commit)
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files")

    # Check the distribution
    session.install("setuptools", "twine", "wheel")
    session.run("python", "setup.py", "--quiet", "sdist", "bdist_wheel")
    session.run("twine", "check", *glob.glob("dist/*"))


@nox.session(python="3.8")
def docs(session):
    shutil.rmtree("docs/_build", ignore_errors=True)
    session.install("sphinx", "sphinx-rtd-theme")

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


@nox.session
def release(session):
    package_name = "packaging"
    version_file = Path(f"{package_name}/__about__.py")

    try:
        release_version = _get_version_from_arguments(session.posargs)
    except ValueError as e:
        session.error(f"Invalid arguments: {e}")

    # Check state of working directory and git
    _check_working_directory_state(session)
    _check_git_state(session, release_version)

    # Bump to release version
    _bump(session, version=release_version, file=version_file, kind="release")

    # Tag the release commit
    session.run("git", "tag", "-s", release_version, external=True)

    # Bump for development
    major, minor = map(int, release_version.split("."))
    next_version = f"{major}.{minor + 1}.dev0"
    _bump(session, version=next_version, file=version_file, kind="development")

    # Checkout the git tag
    session.run("git", "checkout", "-q", release_version, external=True)

    # Build the distribution
    session.run("python", "setup.py", "sdist", "bdist_wheel")

    # Check what files are in dist/ for upload.
    files = glob.glob(f"dist/*")
    assert sorted(files) == [
        f"dist/{package_name}-{release_version}.tag.gz",
        f"dist/{package_name}-{release_version}-py2.py3-none-any.whl",
    ], f"Got the wrong files: {files}"

    # Get back out into master
    session.run("git", "checkout", "-q", "master", external=True)

    # Check and upload distribution files
    session.run("twine", "check", *files)

    # Upload the distribution
    session.run("twine", "upload", *files)

    # Push the commits and tag
    # NOTE: The following fails if pushing to the branch is not allowed. This can
    #       happen on GitHub, if the master branch is protected, there are required
    #       CI checks and "Include administrators" is enabled on the protection.
    session.run("git", "push", "upstream", "master", release_version, external=True)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _get_version_from_arguments(arguments):
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


def _check_working_directory_state(session):
    """Check state of the working directory, prior to making the release.
    """
    should_not_exist = ["build/", "dist/"]

    bad_existing_paths = list(filter(os.path.exists, should_not_exist))
    if bad_existing_paths:
        session.error(f"Remove {', '.join(bad_existing_paths)} and try again")


def _check_git_state(session, version_tag):
    """Check state of the git repository, prior to making the release.
    """
    # Ensure the upstream remote pushes to correct URL
    allowed_upstreams = [
        "git@github.com:pypa/packaging.git",
        "https://github.com/pypa/packaging.git",
    ]
    result = subprocess.run(
        ["git", "remote", "get-url", "--push", "upstream"],
        capture_output=True,
        encoding="utf-8",
    )
    if result.stdout.rstrip() not in allowed_upstreams:
        session.error(f"git remote `upstream` is not one of {allowed_upstreams}")
    # Ensure we're on master branch for cutting a release.
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        encoding="utf-8",
    )
    if result.stdout != "master\n":
        session.error(f"Not on master branch: {result.stdout!r}")

    # Ensure there are no uncommitted changes.
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, encoding="utf-8"
    )
    if result.stdout:
        print(result.stdout, end="")
        session.error(f"The working tree has uncommitted changes")

    # Ensure this tag doesn't exist already.
    result = subprocess.run(
        ["git", "rev-parse", version_tag], capture_output=True, encoding="utf-8"
    )
    if not result.returncode:
        session.error(f"Tag already exists! {version_tag} -- {result.stdout!r}")

    # Back up the current git reference, in a tag that's easy to clean up.
    _release_backup_tag = "auto/release-start-" + str(int(time.time()))
    session.run("git", "tag", _release_backup_tag, external=True)


def _bump(session, *, version, file, kind):
    session.log(f"Bump version to {version!r}")
    contents = file.read_text()
    new_contents = re.sub(
        '__version__ = "(.+)"', f'__version__ = "{version}"', contents
    )
    file.write_text(new_contents)

    session.log(f"git commit")
    subprocess.run(["git", "add", str(file)])
    subprocess.run(["git", "commit", "-m", f"Bump for {kind}"])
