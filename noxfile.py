# mypy: disallow-untyped-defs=False, disallow-untyped-calls=False

import glob
import shutil

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
    session.install("setuptools", "readme_renderer", "twine", "wheel")
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
