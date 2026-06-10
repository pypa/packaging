from pathlib import Path

from packaging.project import parse
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version


def test_simple_pass(tmp_path: Path):
    result = parse({"project": {"name": "foo", "version": "0.0.1"}}, tmp_path)
    assert not result.errors, result.errors
    assert result.data == {"name": "foo", "version": Version("0.0.1")}


def test_simple_fail(tmp_path: Path):
    result = parse({"project": {}}, tmp_path)
    assert [e.key for e in result.errors] == ["project.name", "project.version"]


def test_full_pass(tmp_path: Path):
    tmp_path.joinpath("README.md").write_text("# title")
    tmp_path.joinpath("LICENSE.txt").write_text("MIT")
    result = parse(
        {
            "project": {
                "name": "foo",
                "version": "0.0.1",
                "description": "foo bar",
                "readme": "README.md",
                "license": {"file": "LICENSE.txt"},
                "urls": {"homepage": "https://example.com"},
                "keywords": ["foo", "bar"],
                "authors": [{"name": "Bob Geldof", "email": "a@bcom"}],
                "classifiers": ["Development Status :: 4 - Beta"],
                "requires-python": ">=3.6",
                "dependencies": ["bar>=1.0", "baz"],
                "optional-dependencies": {"foo": ["bar"]},
                "scripts": {"foo": "bar"},
                "gui-scripts": {"foo": "bar"},
                "entry-points": {"other": {"foo": "bar"}},
            }
        },
        tmp_path,
    )
    assert not result.errors, result.errors
    assert result.data == {
        "name": "foo",
        "version": Version("0.0.1"),
        "description": "foo bar",
        "readme_text": "# title",
        "readme_content_type": "text/markdown",
        "readme_path": tmp_path / "README.md",
        "license_text": "MIT",
        "license_path": tmp_path / "LICENSE.txt",
        "urls": {"homepage": "https://example.com"},
        "keywords": ["foo", "bar"],
        "authors": [{"name": "Bob Geldof", "email": "a@bcom"}],
        "classifiers": ["Development Status :: 4 - Beta"],
        "requires_python": SpecifierSet(">=3.6"),
        "dependencies": [Requirement("bar>=1.0"), Requirement("baz")],
        "optional_dependencies": {"foo": [Requirement("bar")]},
        "entry_points": {
            "console_scripts": {"foo": "bar"},
            "gui_scripts": {"foo": "bar"},
            "other": {"foo": "bar"},
        },
    }
