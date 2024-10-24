# SPDX-License-Identifier: MIT

from __future__ import annotations

import inspect

import packaging.metadata
import packaging.project


def test_convert_optional_dependencies() -> None:
    metadata = packaging.project.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "version": "0.1.0",
                "optional-dependencies": {
                    "test": [
                        'foo; os_name == "nt" or sys_platform == "win32"',
                        'bar; os_name == "posix" and sys_platform == "linux"',
                    ],
                },
            },
        }
    )
    message = metadata.metadata(metadata_version="2.1").as_rfc822()
    requires = message.get_all("requires-dist")
    assert requires == [
        'foo; (os_name == "nt" or sys_platform == "win32") and extra == "test"',
        'bar; os_name == "posix" and sys_platform == "linux" and extra == "test"',
    ]


def test_convert_author_email() -> None:
    metadata = packaging.project.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "version": "0.1.0",
                "authors": [
                    {
                        "name": "John Doe, Inc.",
                        "email": "johndoe@example.com",
                    },
                    {
                        "name": "Kate Doe, LLC.",
                        "email": "katedoe@example.com",
                    },
                ],
            },
        }
    )
    message = metadata.metadata(metadata_version="2.3").as_rfc822()
    assert message.get_all("Author-Email") == [
        '"John Doe, Inc." <johndoe@example.com>, "Kate Doe, LLC." <katedoe@example.com>'
    ]


def test_long_version() -> None:
    metadata = packaging.project.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "version": "0.0.0+super.duper.long.version.string.that.is.longer.than.sixty.seven.characters",
            }
        }
    )
    message = metadata.metadata(metadata_version="2.1").as_rfc822()
    assert (
        message.get("Version")
        == "0.0.0+super.duper.long.version.string.that.is.longer.than.sixty.seven.characters"
    )
    assert (
        bytes(message)
        == inspect.cleandoc(
            """
        metadata-version: 2.1
        name: example
        version: 0.0.0+super.duper.long.version.string.that.is.longer.than.sixty.seven.characters
    """
        ).encode("utf-8")
        + b"\n\n"
    )
    assert (
        str(message)
        == inspect.cleandoc(
            """
        metadata-version: 2.1
        name: example
        version: 0.0.0+super.duper.long.version.string.that.is.longer.than.sixty.seven.characters
    """
        )
        + "\n\n"
    )
