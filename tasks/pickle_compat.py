# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Generate or verify pickle files with packaging objects for cross-version testing.

Usage:
    python tasks/pickle_compat.py write <version> <output_dir>
    python tasks/pickle_compat.py verify [--version <version>] <pickle_file>

The ``write`` command generates a pickle file using the *currently installed*
release of ``packaging``.  ``<version>`` is recorded as metadata in the file
(e.g. ``25.0``) so that ``verify`` can report what release created the pickle.

The ``verify`` command loads a pickle and checks that every object:

* has the expected type,
* compares equal to a freshly constructed counterpart, and
* round-trips through ``pickle.dumps`` / ``pickle.loads``.

When ``--version`` is supplied, ``verify`` also checks that the pickle was
generated with that release of ``packaging``.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import pathlib
import pickle
import sys
from typing import Any

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import Specifier, SpecifierSet
from packaging.tags import Tag
from packaging.version import Version

_HASHES = {"sha256": "f" * 40}

_PYLOCK = {
    "lock-version": "1.0",
    "created-by": "pip",
    "environments": ["os_name == 'posix'"],
    "requires-python": ">=3.10",
    "packages": [
        {
            "name": "a",
            "version": "1.0",
            "marker": "os_name == 'posix'",
            "sdist": {"url": "https://e.com/a-1.0.tar.gz", "hashes": _HASHES},
            "wheels": [
                {"url": "https://e.com/a-1.0-py3-none-any.whl", "hashes": _HASHES}
            ],
        },
        {
            "name": "b",
            "vcs": {"type": "git", "url": "https://g.c/b.git", "commit-id": "a" * 40},
        },
        {"name": "c", "directory": {"path": "c", "editable": True}},
        {"name": "d", "archive": {"url": "https://e.com/d.zip", "hashes": _HASHES}},
    ],
    "tool": {"x": {"y": 1}},
}

_DIRECT_URLS = [
    {"url": "file:///p", "dir_info": {"editable": True}},
    {
        "url": "https://e.com/a.zip",
        "archive_info": {"hashes": _HASHES},
        "subdirectory": "sub",
    },
    {
        "url": "https://g.c/r.git",
        "vcs_info": {"vcs": "git", "commit_id": "a" * 40, "requested_revision": "v1"},
    },
]


def _objects() -> dict[str, list[Any]]:
    """Objects to pickle, limited to what the installed packaging provides."""
    objects: dict[str, list[Any]] = {
        "version": [
            Version("1.2.3"),
            Version("1!2.3.4a5.post6.dev7+zzz"),
            Version("0.1.0"),
            Version("2.0a1"),
            Version("1.0.post1"),
            Version("1.0.dev3"),
        ],
        "marker": [
            Marker('python_version >= "3.8"'),
            Marker('os_name == "posix" and python_version >= "3.9"'),
            Marker('extra == "test"'),
        ],
        "specifier": [
            Specifier(">=1.0.0"),
            Specifier("~=2.3"),
            Specifier("==1.2.*"),
            Specifier("!=2.0.0"),
            Specifier("<3.0"),
            Specifier(">1.0"),
            Specifier("<=2.0"),
        ],
        "specifierset": [
            SpecifierSet(">=1.0.0,<2.0.0"),
            SpecifierSet("~=1.0,!=1.0.1"),
            SpecifierSet(">=3.0"),
        ],
        "tag": [
            Tag("cp39", "cp39", "linux_x86_64"),
            Tag("py3", "none", "any"),
            Tag("cp310", "abi3", "manylinux_2_17_x86_64"),
        ],
        "requirement": [
            Requirement("name"),
            Requirement("name[a,b]>=1.0,<2; python_version >= '3.8'"),
            Requirement("name @ https://e.com/name-1.0.tar.gz"),
        ],
    }

    try:
        from packaging.pylock import Pylock  # noqa: PLC0415
    except ImportError:  # Added in 26.0.
        pass
    else:
        objects["pylock"] = [Pylock.from_dict(_PYLOCK)]

    try:
        from packaging.direct_url import DirectUrl  # noqa: PLC0415
    except ImportError:  # Added in 26.1.
        pass
    else:
        objects["direct_url"] = [DirectUrl.from_dict(d) for d in _DIRECT_URLS]

    return objects


def write(version: str, output_dir: pathlib.Path) -> pathlib.Path:
    """Pickle a representative set of objects and write them to disk."""
    installed = importlib.metadata.version("packaging")
    if version != installed:
        raise SystemExit(
            f"Requested packaging=={version} but the installed version is {installed}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"packaging_{version}_pickles.pkl"

    with open(path, "wb") as f:
        pickle.dump({"generated_with": version, "objects": _objects()}, f)

    return path


def verify(path: pathlib.Path, expected_version: str | None = None) -> int:
    """Load a pickle file and verify its contents.

    Returns 0 on success, 1 on failure.
    """
    with open(path, "rb") as f:
        data: dict[str, Any] = pickle.load(f)  # noqa: S301

    generated_with = data["generated_with"]
    objects: dict[str, list[Any]] = data["objects"]
    print(f"Verifying pickles generated with packaging=={generated_with}")

    if expected_version is not None and generated_with != expected_version:
        print(
            f"FAIL: generated_with ({generated_with}) != expected version "
            f"({expected_version})",
            file=sys.stderr,
        )
        return 1

    current = _objects()
    for kind, loaded_list in objects.items():
        expected_list = current[kind]

        if len(loaded_list) != len(expected_list):
            print(
                f"FAIL: {kind} list length mismatch "
                f"({len(loaded_list)} vs {len(expected_list)})",
                file=sys.stderr,
            )
            return 1

        for i, (loaded, expected) in enumerate(
            zip(loaded_list, expected_list, strict=True)
        ):
            if type(loaded) is not type(expected):
                print(
                    f"FAIL: {kind}[{i}] is {type(loaded).__name__}, "
                    f"expected {type(expected).__name__}",
                    file=sys.stderr,
                )
                return 1

            if loaded != expected:
                print(
                    f"FAIL: {kind}[{i}] {loaded!r} != {expected!r}",
                    file=sys.stderr,
                )
                return 1

            reloaded = pickle.loads(pickle.dumps(loaded))  # noqa: S301
            if reloaded != expected:
                print(
                    f"FAIL: {kind}[{i}] does not round-trip correctly",
                    file=sys.stderr,
                )
                return 1

    print("All pickle verifications passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write", help="Generate a pickle file")
    write_parser.add_argument(
        "version", help="packaging version generating the pickles"
    )
    write_parser.add_argument(
        "output_dir",
        type=pathlib.Path,
        default=pathlib.Path("."),
        nargs="?",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify a pickle file")
    verify_parser.add_argument(
        "pickle_file", type=pathlib.Path, help="path to the pickle file"
    )
    verify_parser.add_argument(
        "--version", dest="expected_version", help="expected packaging version"
    )

    args = parser.parse_args()

    if args.command == "write":
        path = write(args.version, args.output_dir)
        print(f"Wrote {path}")
        return 0

    if args.command == "verify":
        return verify(args.pickle_file, args.expected_version)

    return 1


if __name__ == "__main__":
    sys.exit(main())
