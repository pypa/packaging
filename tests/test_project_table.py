from __future__ import annotations

import re
import sys

import pytest

from packaging.project_table import (
    BuildSystemTable,
    IncludeGroupTable,
    ProjectTable,
    PyProjectTable,
    to_project_table,
)

if sys.version_info < (3, 11):
    import tomli as tomllib
else:
    import tomllib


def test_project_table() -> None:
    table = PyProjectTable(
        {
            "build-system": BuildSystemTable(
                {"build-backend": "one", "requires": ["two"]}
            ),
            "project": ProjectTable(
                {
                    "name": "one",
                    "version": "0.1.0",
                }
            ),
            "tool": {"thing": object()},
            "dependency-groups": {
                "one": [
                    "one",
                    IncludeGroupTable({"include-group": "two"}),
                ]
            },
        }
    )

    assert table.get("build-system", {}).get("build-backend", "") == "one"
    assert table.get("project", {}).get("name", "") == "one"
    assert table.get("tool", {}).get("thing") is not None
    assert table.get("dependency-groups", {}).get("one") is not None


def test_project_table_type_only() -> None:
    table: PyProjectTable = {
        "build-system": {"build-backend": "one", "requires": ["two"]},
        "project": {
            "name": "one",
            "version": "0.1.0",
        },
        "tool": {"thing": object()},
        "dependency-groups": {
            "one": [
                "one",
                {"include-group": "two"},
            ]
        },
    }

    assert table.get("build-system", {}).get("build-backend", "") == "one"
    assert table.get("project", {}).get("name", "") == "one"
    assert table.get("tool", {}).get("thing") is not None
    assert table.get("dependency-groups", {}).get("one") is not None


@pytest.mark.parametrize(
    "toml_string",
    [
        pytest.param(
            """
            [build-system]
            build-backend = "one"
            requires = ["two"]

            [project]
            name = "one"
            version = "0.1.0"
            license.text = "MIT"
            authors = [
                { name = "Example Author", email = "author@example.com" },
                { name = "Second Author" },
                { email = "author3@example.com" },
            ]

            [project.entry-points]
            some-ep = { thing = "thing:main" }

            [project.scripts]
            my-script = "thing:cli"

            [project.optional-dependencies]
            test = ["pytest"]

            [tool.thing]

            [dependency-groups]
            one = [
                "one",
                { include-group = "two" },
            ]
            """,
            id="large example",
        ),
        pytest.param(
            """
            [project]
            name = "example"
            """,
            id="minimal example",
        ),
        pytest.param(
            """
            [project]
            name = "example"
            license = "MIT"
            """,
            id="license as str",
        ),
        pytest.param(
            """
            [project]
            name = "example"
            unknown-key = 123
            authors = [
                { other-key = "also ignored" },
            ]
            license.unreal = "ignored as well"
            readme.nothing = "ignored too"
            """,
            id="extra keys are ignored",  # TypedDict's are not complete
        ),
        pytest.param(
            """
            [project]
            name = "example"
            dynamic = ["version", "readme"]
            """,
            id="dynamic field",
        ),
    ],
)
def test_conversion_fn(toml_string: str) -> None:
    data = tomllib.loads(toml_string)
    table = to_project_table(data)
    assert table == data


@pytest.mark.parametrize(
    ("toml_string", "expected_msg"),
    [
        pytest.param(
            """
            [project]
            """,
            'Key "project.name" is required if "project" is present',
            id="missing required project.name",
        ),
        pytest.param(
            """
            [project]
            name = 123
            """,
            '"project.name" expected str, got int',
            id="bad project.name type",
        ),
        pytest.param(
            """
            [build-system]
            build-backend = "one"
            requires = "two"  # should be List[str]

            [project]
            name = "one"
            version = "0.1.0"
            """,
            '"build-system.requires" expected list, got str',
            id="bad build-system.requires type",
        ),
        pytest.param(
            """
            [dependency-groups]
            one = [
                "one",
                { include-group = 123 },  # should be str
            ]

            [project]
            name = "one"
            version = "0.1.0"
            """,
            '"dependency-groups.one[]" does not match any type in str | IncludeGroupTable',
            id="bad nested in dictionary type",
        ),
        pytest.param(
            """
            [project]
            name = "example"
            [project.license]
            text = 123
            """,
            '"project.license" does not match any type in LicenseTable | str',
            id="project.license.text bad nested dict type",
        ),
        pytest.param(
            """
            [project]
            name = "example"
            [project.entry-points]
            console_scripts = { bad = 123 }
            """,
            '"project.entry-points.console_scripts.bad" expected str, got int',
            id="nested dicts of dicts bad type",
        ),
        pytest.param(
            """
            [project]
            name = "example"
            dynamic = ["notreal"]
            """,
            '"project.dynamic[]" expected one of',
            id="Invalid dynamic value",
        ),
        pytest.param(
            """
            [project]
            name = "example"

            [project.optional-dependencies]
            test = "notalist"
            """,
            '"project.optional-dependencies.test" expected list, got str',
            id="bad optional-dependencies type",
        ),
    ],
)
def test_conversion_fn_bad_type(toml_string: str, expected_msg: str) -> None:
    data = tomllib.loads(toml_string)
    with pytest.raises(TypeError, match=re.escape(expected_msg)):
        to_project_table(data)
