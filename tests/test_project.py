# SPDX-License-Identifier: MIT

from __future__ import annotations

import contextlib
import pathlib
import re
import shutil
import sys
import textwrap
import warnings
from typing import TYPE_CHECKING

import pytest

import packaging.errors
import packaging.metadata
import packaging.project
import packaging.specifiers
import packaging.version

if TYPE_CHECKING:
    from collections.abc import Generator

if sys.version_info < (3, 11):
    import tomli as tomllib
else:
    import tomllib


DIR = pathlib.Path(__file__).parent.resolve()
PRE_SPDX_METADATA_VERSIONS = {"2.1", "2.2", "2.3"}


@pytest.fixture(params=("2.1", "2.2", "2.3", "2.4"))
def metadata_version(request: pytest.FixtureRequest) -> str:
    return request.param  # type: ignore[no-any-return]


@contextlib.contextmanager
def raises_single(
    exception_type: type[Exception], contains: str, match: str
) -> Generator[pytest.ExceptionInfo[packaging.errors.ExceptionGroup], None, None]:
    with pytest.raises(packaging.errors.ExceptionGroup, match=match) as excinfo:
        yield excinfo
    assert len(excinfo.value.exceptions) == 1
    assert isinstance(excinfo.value.exceptions[0], exception_type)
    assert contains in str(excinfo.value.exceptions[0])


@pytest.mark.parametrize(
    ("data", "error"),
    [
        pytest.param(
            "",
            'Section "project" missing in pyproject.toml',
            id="Missing project section",
        ),
        pytest.param(
            """
                [project]
                name = true
                version = "0.1.0"
            """,
            'Field "project.name" has an invalid type, expecting a string (got bool)',
            id="Invalid name type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                not-real-key = true
            """,
            "Extra keys present in \"project\": 'not-real-key'",
            id="Invalid project key",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dynamic = [
                    "name",
                ]
            """,
            "Unsupported field 'name' in \"project.dynamic\"",
            id="Unsupported field in project.dynamic",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dynamic = [
                    3,
                ]
            """,
            'Field "project.dynamic" contains item with invalid type, expecting a string (got int)',
            id="Unsupported type in project.dynamic",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = true
            """,
            'Field "project.version" has an invalid type, expecting a string (got bool)',
            id="Invalid version type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
            """,
            'Field "project.version" missing and \'version\' not specified in "project.dynamic"',
            id="Missing version",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0-extra"
            """,
            "Invalid \"project.version\" value, expecting a valid PEP 440 version (got '0.1.0-extra')",
            id="Invalid version value",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = true
            """,
            'Field "project.license" has an invalid type, expecting a string or table of strings (got bool)',
            id="License invalid type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = {}
            """,
            'Invalid "project.license" contents, expecting a string or one key "file" or "text" (got {})',
            id="Missing license keys",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { file = "...", text = "..." }
            """,
            (
                'Invalid "project.license" contents, expecting a string or one key "file" or "text"'
                " (got {'file': '...', 'text': '...'})"
            ),
            id="Both keys for license",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { made-up = ":(" }
            """,
            'Unexpected field "project.license.made-up"',
            id="Got made-up license field",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { file = true }
            """,
            'Field "project.license.file" has an invalid type, expecting a string (got bool)',
            id="Invalid type for license.file",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { text = true }
            """,
            'Field "project.license.text" has an invalid type, expecting a string (got bool)',
            id="Invalid type for license.text",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { file = "this-file-does-not-exist" }
            """,
            "License file not found ('this-file-does-not-exist')",
            id="License file not present",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = true
            """,
            (
                'Field "project.readme" has an invalid type, expecting either '
                "a string or table of strings (got bool)"
            ),
            id="Invalid readme type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = {}
            """,
            'Invalid "project.readme" contents, expecting either "file" or "text" (got {})',
            id="Empty readme table",
        ),
        pytest.param(
            """
                [project]
                name = 'test'
                version = "0.1.0"
                readme = "README.jpg"
            """,
            "Could not infer content type for readme file 'README.jpg'",
            id="Unsupported filename in readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = "...", text = "..." }
            """,
            (
                'Invalid "project.readme" contents, expecting either "file" or "text"'
                " (got {'file': '...', 'text': '...'})"
            ),
            id="Both readme fields",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { made-up = ":(" }
            """,
            'Unexpected field "project.readme.made-up"',
            id="Unexpected field in readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = true }
            """,
            'Field "project.readme.file" has an invalid type, expecting a string (got bool)',
            id="Invalid type for readme.file",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { text = true }
            """,
            'Field "project.readme.text" has an invalid type, expecting a string (got bool)',
            id="Invalid type for readme.text",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = "this-file-does-not-exist", content-type = "..." }
            """,
            "Readme file not found ('this-file-does-not-exist')",
            id="Readme file not present",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = "README.md" }
            """,
            'Field "project.readme.content-type" missing',
            id="Missing content-type for readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = 'README.md', content-type = true }
            """,
            'Field "project.readme.content-type" has an invalid type, expecting a string (got bool)',
            id="Wrong content-type type for readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { text = "..." }
            """,
            'Field "project.readme.content-type" missing',
            id="Missing content-type for readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                description = true
            """,
            'Field "project.description" has an invalid type, expecting a string (got bool)',
            id="Invalid description type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dependencies = "some string!"
            """,
            'Field "project.dependencies" has an invalid type, expecting a list of strings (got str)',
            id="Invalid dependencies type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dependencies = [
                    99,
                ]
            """,
            'Field "project.dependencies" contains item with invalid type, expecting a string (got int)',
            id="Invalid dependencies item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dependencies = [
                    "definitely not a valid PEP 508 requirement!",
                ]
            """,
            (
                'Field "project.dependencies" contains an invalid PEP 508 requirement '
                "string 'definitely not a valid PEP 508 requirement!' "
            ),
            id="Invalid dependencies item",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                optional-dependencies = true
            """,
            (
                'Field "project.optional-dependencies" has an invalid type, '
                "expecting a table of PEP 508 requirement strings (got bool)"
            ),
            id="Invalid optional-dependencies type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.optional-dependencies]
                test = "some string!"
            """,
            (
                'Field "project.optional-dependencies.test" has an invalid type, '
                "expecting a table of PEP 508 requirement strings (got str)"
            ),
            id="Invalid optional-dependencies not list",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.optional-dependencies]
                test = [
                    true,
                ]
            """,
            (
                'Field "project.optional-dependencies.test" has an invalid type, '
                "expecting a PEP 508 requirement string (got bool)"
            ),
            id="Invalid optional-dependencies item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.optional-dependencies]
                test = [
                    "definitely not a valid PEP 508 requirement!",
                ]
            """,
            (
                'Field "project.optional-dependencies.test" contains an invalid '
                "PEP 508 requirement string 'definitely not a valid PEP 508 requirement!' "
            ),
            id="Invalid optional-dependencies item",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                requires-python = true
            """,
            'Field "project.requires-python" has an invalid type, expecting a string (got bool)',
            id="Invalid requires-python type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                requires-python = "3.8"
            """,
            "Invalid \"project.requires-python\" value, expecting a valid specifier set (got '3.8')",
            id="Invalid requires-python value",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                keywords = "some string!"
            """,
            'Field "project.keywords" has an invalid type, expecting a list of strings (got str)',
            id="Invalid keywords type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                keywords = [3]
            """,
            'Field "project.keywords" contains item with invalid type, expecting a string (got int)',
            id="Invalid keyword type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                keywords = [
                    true,
                ]
            """,
            'Field "project.keywords" contains item with invalid type, expecting a string (got bool)',
            id="Invalid keywords item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                authors = {}
            """,
            (
                'Field "project.authors" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got dict)'
            ),
            id="Invalid authors type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                authors = [
                    true,
                ]
            """,
            (
                'Field "project.authors" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got list with bool)'
            ),
            id="Invalid authors item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                maintainers = {}
            """,
            (
                'Field "project.maintainers" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got dict)'
            ),
            id="Invalid maintainers type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                maintainers = [
                    10
                ]
            """,
            (
                'Field "project.maintainers" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got list with int)'
            ),
            id="Invalid maintainers item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                maintainers = [
                    {"name" = 12}
                ]
            """,
            (
                'Field "project.maintainers" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got list with dict with int)'
            ),
            id="Invalid maintainers nested type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                maintainers = [
                    {"name" = "me", "other" = "you"}
                ]
            """,
            (
                'Field "project.maintainers" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got list with dict with extra keys "other")'
            ),
            id="Invalid maintainers nested type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                classifiers = "some string!"
            """,
            'Field "project.classifiers" has an invalid type, expecting a list of strings (got str)',
            id="Invalid classifiers type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                classifiers = [
                    true,
                ]
            """,
            'Field "project.classifiers" contains item with invalid type, expecting a string (got bool)',
            id="Invalid classifiers item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                homepage = true
            """,
            'Field "project.urls.homepage" has an invalid type, expecting a string (got bool)',
            id="Invalid urls homepage type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                Documentation = true
            """,
            'Field "project.urls.Documentation" has an invalid type, expecting a string (got bool)',
            id="Invalid urls documentation type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                repository = true
            """,
            'Field "project.urls.repository" has an invalid type, expecting a string (got bool)',
            id="Invalid urls repository type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                "I am really really too long for this place" = "url"
            """,
            "\"project.urls\" names cannot be more than 32 characters long (got 'I am really really too long for this place')",
            id="URL name too long",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                changelog = true
            """,
            'Field "project.urls.changelog" has an invalid type, expecting a string (got bool)',
            id="Invalid urls changelog type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                scripts = []
            """,
            'Field "project.scripts" has an invalid type, expecting a table of strings (got list)',
            id="Invalid scripts type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                gui-scripts = []
            """,
            'Field "project.gui-scripts" has an invalid type, expecting a table of strings (got list)',
            id="Invalid gui-scripts type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                entry-points = []
            """,
            (
                'Field "project.entry-points" has an invalid type, '
                "expecting a table of entrypoint sections (got list)"
            ),
            id="Invalid entry-points type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                entry-points = { section = "something" }
            """,
            (
                'Field "project.entry-points.section" has an invalid type, '
                "expecting a table of entrypoints (got str)"
            ),
            id="Invalid entry-points section type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.entry-points.section]
                entrypoint = []
            """,
            'Field "project.entry-points.section.entrypoint" has an invalid type, expecting a string (got list)',
            id="Invalid entry-points entrypoint type",
        ),
        pytest.param(
            """
                [project]
                name = ".test"
                version = "0.1.0"
            """,
            (
                "Invalid project name '.test'. A valid name consists only of ASCII letters and "
                "numbers, period, underscore and hyphen. It must start and end with a letter or number"
            ),
            id="Invalid project name",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.entry-points.bad-name]
            """,
            (
                'Field "project.entry-points" has an invalid value, expecting a name containing only '
                "alphanumeric, underscore, or dot characters (got 'bad-name')"
            ),
            id="Invalid entry-points name",
        ),
        # both license files and classic license are not allowed
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = []
                license.text = 'stuff'
            """,
            '"project.license-files" must not be used when "project.license" is not a SPDX license expression',
            id="Both license files and classic license",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = ['../LICENSE']
            """,
            "'../LICENSE' is an invalid \"project.license-files\" glob: the pattern must match files within the project directory",
            id="Parent license-files glob",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = [12]
            """,
            'Field "project.license-files" contains item with invalid type, expecting a string (got int)',
            id="Parent license-files invalid type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = ['this', 12]
            """,
            'Field "project.license-files" contains item with invalid type, expecting a string (got int)',
            id="Parent license-files invalid type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = ['/LICENSE']
            """,
            "'/LICENSE' is an invalid \"project.license-files\" glob: the pattern must match files within the project directory",
            id="Absolute license-files glob",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = 'MIT'
                classifiers = ['License :: OSI Approved :: MIT License']
            """,
            "Setting \"project.license\" to an SPDX license expression is not compatible with 'License ::' classifiers",
            id="SPDX license and License trove classifiers",
        ),
    ],
)
def test_load(data: str, error: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "project/full-metadata")
    with warnings.catch_warnings():
        warnings.simplefilter(
            action="ignore", category=packaging.errors.ConfigurationWarning
        )
        with raises_single(
            packaging.errors.ConfigurationError, error, "Failed to parse pyproject.toml"
        ):
            packaging.project.StandardMetadata.from_pyproject(
                tomllib.loads(textwrap.dedent(data)),
            )


@pytest.mark.parametrize(
    ("data", "errors"),
    [
        pytest.param(
            "[project]",
            [
                'Field "project.name" missing',
                'Field "project.version" missing and \'version\' not specified in "project.dynamic"',
            ],
            id="Missing project name",
        ),
        pytest.param(
            """
                [project]
                name = true
                version = "0.1.0"
                dynamic = [
                    "name",
                ]
            """,
            [
                "Unsupported field 'name' in \"project.dynamic\"",
                'Field "project.name" has an invalid type, expecting a string (got bool)',
            ],
            id="Unsupported field in project.dynamic",
        ),
        pytest.param(
            """
                [project]
                name = true
                version = "0.1.0"
                dynamic = [
                    3,
                ]
            """,
            [
                'Field "project.dynamic" contains item with invalid type, expecting a string (got int)',
                'Field "project.name" has an invalid type, expecting a string (got bool)',
            ],
            id="Unsupported type in project.dynamic",
        ),
        pytest.param(
            """
                [project]
                name = 'test'
                version = "0.1.0"
                readme = "README.jpg"
                license-files = [12]
            """,
            [
                'Field "project.license-files" contains item with invalid type, expecting a string (got int)',
                "Could not infer content type for readme file 'README.jpg'",
            ],
            id="Unsupported filename in readme",
        ),
        pytest.param(
            """
                [project]
                name = 'test'
                version = "0.1.0"
                readme = "README.jpg"
                license-files = [12]
                entry-points.bad-name = {}
                other-entry = {}
                not-valid = true
            """,
            [
                "Extra keys present in \"project\": 'not-valid', 'other-entry'",
                'Field "project.license-files" contains item with invalid type, expecting a string (got int)',
                "Could not infer content type for readme file 'README.jpg'",
                "Field \"project.entry-points\" has an invalid value, expecting a name containing only alphanumeric, underscore, or dot characters (got 'bad-name')",
            ],
            id="Four errors including extra keys",
        ),
    ],
)
def test_load_multierror(
    data: str, errors: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "project/full-metadata")
    with warnings.catch_warnings():
        warnings.simplefilter(
            action="ignore", category=packaging.errors.ConfigurationWarning
        )
        with pytest.raises(packaging.errors.ExceptionGroup) as execinfo:
            packaging.project.StandardMetadata.from_pyproject(
                tomllib.loads(textwrap.dedent(data)),
            )
    exceptions = execinfo.value.exceptions
    args = [e.args[0] for e in exceptions]
    assert len(args) == len(errors)
    assert args == errors
    assert "Failed to parse pyproject.toml" in repr(execinfo.value)


@pytest.mark.parametrize(
    ("data", "error", "metadata_version"),
    [
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = 'MIT'
            """,
            'Setting "project.license" to an SPDX license expression is supported only when emitting metadata version >= 2.4',
            "2.3",
            id="SPDX with metadata_version 2.3",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = ['README.md']
            """,
            '"project.license-files" is supported only when emitting metadata version >= 2.4',
            "2.3",
            id="license-files with metadata_version 2.3",
        ),
    ],
)
def test_load_with_metadata_version(
    data: str, error: str, metadata_version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "project/full-metadata")
    with raises_single(
        packaging.errors.ConfigurationError, error, "Metadata validation failed"
    ):
        packaging.project.StandardMetadata.from_pyproject(
            tomllib.loads(textwrap.dedent(data))
        ).metadata(metadata_version=metadata_version)


@pytest.mark.parametrize(
    ("data", "error", "metadata_version"),
    [
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license.text = 'MIT'
            """,
            'Set "project.license" to an SPDX license expression for metadata >= 2.4',
            "2.4",
            id="Classic license with metadata 2.4",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                classifiers = ['License :: OSI Approved :: MIT License']
            """,
            "'License ::' classifiers are deprecated for metadata >= 2.4, use a SPDX license expression for \"project.license\" instead",
            "2.4",
            id="License trove classifiers with metadata 2.4",
        ),
    ],
)
def test_load_with_metadata_version_warnings(
    data: str, error: str, metadata_version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "project/full-metadata")
    with pytest.warns(packaging.errors.ConfigurationWarning, match=re.escape(error)):
        packaging.project.StandardMetadata.from_pyproject(
            tomllib.loads(textwrap.dedent(data))
        ).metadata(metadata_version=metadata_version)


@pytest.mark.parametrize("after_rfc", [False, True])
def test_value(after_rfc: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "project/full-metadata")
    with open("pyproject.toml", "rb") as f:
        metadata = packaging.project.StandardMetadata.from_pyproject(tomllib.load(f))

    if after_rfc:
        metadata.metadata(metadata_version="2.2").as_rfc822()

    assert metadata.dynamic == []
    assert metadata.name == "full_metadata"
    assert metadata.canonical_name == "full-metadata"
    assert metadata.version == packaging.version.Version("3.2.1")
    assert metadata.requires_python == packaging.specifiers.Specifier(">=3.8")
    assert isinstance(metadata.license, packaging.project.License)
    assert metadata.license.file is None
    assert metadata.license.text == "some license text"
    assert isinstance(metadata.readme, packaging.project.Readme)
    assert metadata.readme.file == pathlib.Path("README.md")
    assert metadata.readme.text == pathlib.Path("README.md").read_text(encoding="utf-8")
    assert metadata.readme.content_type == "text/markdown"
    assert metadata.description == "A package with all the metadata :)"
    assert metadata.authors == [
        ("Unknown", "example@example.com"),
        ("Example!", None),
    ]
    assert metadata.maintainers == [
        ("Other Example", "other@example.com"),
    ]
    assert metadata.keywords == ["trampolim", "is", "interesting"]
    assert metadata.classifiers == [
        "Development Status :: 4 - Beta",
        "Programming Language :: Python",
    ]
    assert metadata.urls == {
        "changelog": "github.com/some/repo/blob/master/CHANGELOG.rst",
        "documentation": "readthedocs.org",
        "homepage": "example.com",
        "repository": "github.com/some/repo",
    }
    assert metadata.entrypoints == {
        "custom": {
            "full-metadata": "full_metadata:main_custom",
        },
    }
    assert metadata.scripts == {
        "full-metadata": "full_metadata:main_cli",
    }
    assert metadata.gui_scripts == {
        "full-metadata-gui": "full_metadata:main_gui",
    }
    assert list(map(str, metadata.dependencies)) == [
        "dependency1",
        "dependency2>1.0.0",
        "dependency3[extra]",
        'dependency4; os_name != "nt"',
        'dependency5[other-extra]>1.0; os_name == "nt"',
    ]
    assert list(metadata.optional_dependencies.keys()) == ["test"]
    assert list(map(str, metadata.optional_dependencies["test"])) == [
        "test_dependency",
        "test_dependency[test_extra]",
        'test_dependency[test_extra2]>3.0; os_name == "nt"',
    ]


def test_read_license(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "project/full-metadata2")
    with open("pyproject.toml", "rb") as f:
        metadata = packaging.project.StandardMetadata.from_pyproject(tomllib.load(f))

    assert isinstance(metadata.license, packaging.project.License)
    assert metadata.license.file == pathlib.Path("LICENSE")
    assert metadata.license.text == "Some license! 👋\n"


@pytest.mark.parametrize(
    ("package", "content_type"),
    [
        ("full-metadata", "text/markdown"),
        ("full-metadata2", "text/x-rst"),
    ],
)
def test_readme_content_type(
    package: str, content_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "project" / package)
    with open("pyproject.toml", "rb") as f:
        metadata = packaging.project.StandardMetadata.from_pyproject(tomllib.load(f))

    assert isinstance(metadata.readme, packaging.project.Readme)
    assert metadata.readme.content_type == content_type


def test_readme_content_type_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "project/unknown-readme-type")
    with raises_single(
        packaging.errors.ConfigurationError,
        "Could not infer content type for readme file 'README.just-made-this-up-now'",
        "Failed to parse pyproject.toml",
    ), open("pyproject.toml", "rb") as f:
        packaging.project.StandardMetadata.from_pyproject(tomllib.load(f))


def test_as_rfc822(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "project/full-metadata")

    with open("pyproject.toml", "rb") as f:
        metadata = packaging.project.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.metadata(metadata_version="2.1").as_rfc822()
    assert core_metadata.items() == [
        ("metadata-version", "2.1"),
        ("name", "full_metadata"),
        ("version", "3.2.1"),
        ("summary", "A package with all the metadata :)"),
        ("description-content-type", "text/markdown"),
        ("keywords", "trampolim,is,interesting"),
        ("author", "Example!"),
        ("author-email", "Unknown <example@example.com>"),
        ("maintainer-email", "Other Example <other@example.com>"),
        ("license", "some license text"),
        ("classifier", "Development Status :: 4 - Beta"),
        ("classifier", "Programming Language :: Python"),
        ("requires-dist", "dependency1"),
        ("requires-dist", "dependency2>1.0.0"),
        ("requires-dist", "dependency3[extra]"),
        ("requires-dist", 'dependency4; os_name != "nt"'),
        ("requires-dist", 'dependency5[other-extra]>1.0; os_name == "nt"'),
        ("requires-dist", 'test_dependency; extra == "test"'),
        ("requires-dist", 'test_dependency[test_extra]; extra == "test"'),
        (
            "requires-dist",
            'test_dependency[test_extra2]>3.0; os_name == "nt" and extra == "test"',
        ),
        ("requires-python", ">=3.8"),
        ("project-url", "homepage, example.com"),
        ("project-url", "documentation, readthedocs.org"),
        ("project-url", "repository, github.com/some/repo"),
        ("project-url", "changelog, github.com/some/repo/blob/master/CHANGELOG.rst"),
        ("provides-extra", "test"),
    ]
    assert core_metadata.get_payload() == "some readme 👋\n"


def test_as_rfc822_spdx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "project/spdx")

    with open("pyproject.toml", "rb") as f:
        metadata = packaging.project.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.metadata(metadata_version="2.4").as_rfc822()
    assert core_metadata.items() == [
        ("metadata-version", "2.4"),
        ("name", "example"),
        ("version", "1.2.3"),
        ("license-expression", "MIT OR GPL-2.0-or-later OR (FSFUL AND BSD-2-Clause)"),
        ("license-file", "AUTHORS.txt"),
        ("license-file", "LICENSE.md"),
        ("license-file", "LICENSE.txt"),
        ("license-file", "licenses/LICENSE.MIT"),
    ]

    assert core_metadata.get_payload() is None


def test_as_rfc822_spdx_empty_glob(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    shutil.copytree(DIR / "project/spdx", tmp_path / "spdx")
    monkeypatch.chdir(tmp_path / "spdx")

    pathlib.Path("AUTHORS.txt").unlink()
    msg = "Every pattern in \"project.license-files\" must match at least one file: 'AUTHORS*' did not match any"

    with open("pyproject.toml", "rb") as f:
        with pytest.raises(
            packaging.errors.ExceptionGroup,
        ) as execinfo:
            packaging.project.StandardMetadata.from_pyproject(tomllib.load(f))
        assert "Failed to parse pyproject.toml" in str(execinfo.value)
        assert [msg] == [str(e) for e in execinfo.value.exceptions]


def test_license_file_24(
    metadata_version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "project/fulltext_license")
    pre_spdx = metadata_version in PRE_SPDX_METADATA_VERSIONS
    ctx = (
        contextlib.nullcontext()
        if pre_spdx
        else pytest.warns(  # type: ignore[attr-defined]
            packaging.errors.ConfigurationWarning
        )
    )
    with ctx:
        metadata = packaging.project.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "fulltext_license",
                    "version": "0.1.0",
                    "license": {"file": "LICENSE.txt"},
                },
            }
        ).metadata(metadata_version=metadata_version)
    message = str(metadata.as_rfc822())
    if metadata_version in PRE_SPDX_METADATA_VERSIONS:
        assert "license-file: LICENSE.txt" not in message
    else:
        assert "license-file: LICENSE.txt" in message


def test_as_rfc822_dynamic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "project/dynamic-description")

    with open("pyproject.toml", "rb") as f:
        metadata = packaging.project.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.metadata(
        metadata_version="2.3", dynamic_metadata=["description"]
    ).as_rfc822()
    assert core_metadata.items() == [
        ("metadata-version", "2.3"),
        ("name", "dynamic-description"),
        ("version", "1.0.0"),
        ("dynamic", "description"),
    ]


def test_as_rfc822_set_metadata(metadata_version: str) -> None:
    metadata = packaging.project.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "hi",
                "version": "1.2",
                "optional-dependencies": {
                    "under_score": ["some_package"],
                    "da-sh": ["some-package"],
                    "do.t": ["some.package"],
                    "empty": [],
                },
            }
        }
    ).metadata(
        metadata_version=metadata_version,
    )
    assert metadata.metadata_version == metadata_version

    rfc822 = bytes(metadata.as_rfc822()).decode("utf-8")

    assert f"metadata-version: {metadata_version}" in rfc822

    assert "provides-extra: under-score" in rfc822
    assert "provides-extra: da-sh" in rfc822
    assert "provides-extra: do-t" in rfc822
    assert "provides-extra: empty" in rfc822
    assert 'requires-dist: some_package; extra == "under-score"' in rfc822
    assert 'requires-dist: some-package; extra == "da-sh"' in rfc822
    assert 'requires-dist: some.package; extra == "do-t"' in rfc822


def test_as_rfc822_set_metadata_invalid() -> None:
    with raises_single(
        packaging.metadata.InvalidMetadata,
        "'1.9' is not a valid metadata version",
        "invalid metadata",
    ):
        packaging.project.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "hi",
                    "version": "1.2",
                },
            }
        ).metadata(
            metadata_version="1.9",
        )


def test_as_rfc822_invalid_dynamic() -> None:
    metadata = packaging.project.StandardMetadata(
        name="something",
        version=packaging.version.Version("1.0.0"),
    )
    with pytest.raises(
        packaging.errors.ConfigurationError,
        match="Field cannot be set as dynamic metadata: name",
    ):
        metadata.metadata(metadata_version="2.3", dynamic_metadata=["name"])
    with pytest.raises(
        packaging.errors.ConfigurationError,
        match="Field cannot be set as dynamic metadata: version",
    ):
        metadata.metadata(metadata_version="2.3", dynamic_metadata=["version"])
    with pytest.raises(
        packaging.errors.ConfigurationError,
        match="Field is not known: unknown",
    ):
        metadata.metadata(metadata_version="2.3", dynamic_metadata=["unknown"])


def test_as_rfc822_missing_version() -> None:
    metadata = packaging.project.StandardMetadata(name="something")
    with raises_single(
        packaging.errors.ConfigurationError,
        'Missing "project.version" field',
        "Metadata validation failed",
    ):
        metadata.metadata(metadata_version="2.1")


def test_statically_defined_dynamic_field() -> None:
    with raises_single(
        packaging.errors.ConfigurationError,
        'Field "project.version" declared as dynamic in "project.dynamic" but is defined',
        "Failed to parse pyproject.toml",
    ):
        packaging.project.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "example",
                    "version": "1.2.3",
                    "dynamic": [
                        "version",
                    ],
                },
            }
        )


@pytest.mark.parametrize(
    "value",
    [
        "<3.10",
        ">3.7,<3.11",
        ">3.7,<3.11,!=3.8.4",
        "~=3.10,!=3.10.3",
    ],
)
def test_requires_python(value: str) -> None:
    packaging.project.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "version": "0.1.0",
                "requires-python": value,
            },
        }
    )


def test_version_dynamic() -> None:
    metadata = packaging.project.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "dynamic": [
                    "version",
                ],
            },
        }
    )
    metadata.version = packaging.version.Version("1.2.3")


def test_modify_dynamic() -> None:
    metadata = packaging.project.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "version": "1.2.3",
                "dynamic": [
                    "requires-python",
                ],
            },
        }
    )
    metadata.requires_python = packaging.specifiers.SpecifierSet(">=3.12")
    metadata.version = packaging.version.Version("1.2.3")


def test_extra_top_level() -> None:
    assert not packaging.project.extras_top_level(
        {"project": {}, "dependency-groups": {}}
    )
    assert {"also-not-real", "not-real"} == packaging.project.extras_top_level(
        {
            "not-real": {},
            "also-not-real": {},
            "project": {},
            "build-system": {},
        }
    )


def test_extra_build_system() -> None:
    assert not packaging.project.extras_build_system(
        {
            "build-system": {
                "build-backend": "one",
                "requires": ["two"],
                "backend-path": "local",
            },
        }
    )
    assert {"also-not-real", "not-real"} == packaging.project.extras_build_system(
        {
            "build-system": {
                "not-real": {},
                "also-not-real": {},
            }
        }
    )


def test_multiline_description_warns() -> None:
    with raises_single(
        packaging.errors.ConfigurationError,
        'The one-line summary "project.description" should not contain more than one line. Readers might merge or truncate newlines.',
        "Failed to parse pyproject.toml",
    ):
        packaging.project.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "example",
                    "version": "1.2.3",
                    "description": "this\nis multiline",
                },
            }
        )
