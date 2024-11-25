from __future__ import annotations

import re
from typing import Any, cast

from .tags import parse_tag
from .utils import (
    BuildTag,
    InvalidFilename,
    InvalidSdistFilename,
    InvalidWheelFilename,
    _build_tag_regex,
    canonicalize_name,
    is_normalized_name,
)
from .version import InvalidVersion, Version


class Filename:
    def __init__(self, *a: Any, **kw: Any) -> None:
        raise NotImplementedError("Use a WheelFilename or SourceFilename instead")

    @classmethod
    def from_filename(cls, filename: str) -> Filename:
        if filename.endswith(".whl"):
            return WheelFilename.from_filename(filename)
        elif filename.endswith(".tar.gz"):
            return SourceFilename.from_filename(filename)
        else:
            raise InvalidFilename(
                "Invalid filename (extension must be '.whl' or '.tar.gz'): "
                f"{filename!r}"
            )


class WheelFilename(Filename):
    def __init__(
        self,
        name: str,
        version: str,
        build_tag: str | None,
        python_tag: str,
        abi_tag: str,
        platform_tag: str,
        strict: bool = True,
    ) -> None:
        self.original_name = name
        self.original_version = version

        filename = self._to_filename(
            name, version, build_tag, python_tag, abi_tag, platform_tag
        )

        # See PEP 427 for the rules on escaping the project name.
        if (
            strict
            and "__" in name
            or re.match(r"^[\w\d._]*$", name, re.UNICODE) is None
        ):
            raise InvalidWheelFilename(
                f"Invalid filename (invalid project name {name!r}): {filename!r}"
            )

        self.name = canonicalize_name(name).replace("-", "_")

        # Check that the name is normalized
        if strict and self.original_name != self.name:
            raise InvalidWheelFilename(
                f"Invalid filename (non-normalized project name {name!r}): {filename!r}"
            )

        try:
            self.version = Version(version)
        except InvalidVersion as e:
            raise InvalidWheelFilename(
                f"Invalid filename (invalid version {version!r}): {filename!r}"
            ) from e

        # Check that the version is normalized
        if strict and version != str(self.version):
            raise InvalidWheelFilename(
                f"Invalid filename (non-normalized version {version!r}): {filename!r}"
            )

        if build_tag:
            build_match = _build_tag_regex.match(build_tag)
            if build_match is None:
                raise InvalidWheelFilename(
                    f"Invalid filename (invalid build number {build_tag!r}): "
                    f"{filename!r}"
                )
            self.build_tag = cast(
                BuildTag, (int(build_match.group(1)), build_match.group(2))
            )
        else:
            self.build_tag = ()

        self.python_tag = python_tag
        self.abi_tag = abi_tag
        self.platform_tag = platform_tag
        self.tags = parse_tag("-".join((python_tag, abi_tag, platform_tag)))

    def _to_filename(
        self,
        name: str,
        version: str | Version,
        build_tag: str | BuildTag | None,
        python_tag: str,
        abi_tag: str,
        platform_tag: str,
    ) -> str:
        return (
            "-".join(
                part
                for part in [
                    name,
                    str(version),
                    (
                        "".join(str(x) for x in build_tag)
                        if isinstance(build_tag, tuple)
                        else build_tag
                    ),
                    python_tag,
                    abi_tag,
                    platform_tag,
                ]
                if part
            )
            + ".whl"
        )

    def __str__(self) -> str:
        return self._to_filename(
            self.name,
            self.version,
            self.build_tag,
            self.python_tag,
            self.abi_tag,
            self.platform_tag,
        )

    @classmethod
    def from_filename(cls, filename: str) -> WheelFilename:
        if not filename.endswith(".whl"):
            raise InvalidWheelFilename(
                f"Invalid filename (extension must be '.whl'): {filename!r}"
            )

        dashes = filename.count("-")
        if dashes not in (4, 5):
            raise InvalidWheelFilename(
                f"Invalid filename (wrong number of parts): {filename!r}"
            )

        filename = filename[: -len(".whl")]

        # There is no build tag
        if dashes == 4:
            name, version, python_tag, abi_tag, platform_tag = filename.split("-")
            build_tag = None

        # There is a build tag
        if dashes == 5:
            (
                name,
                version,
                build_tag,
                python_tag,
                abi_tag,
                platform_tag,
            ) = filename.split("-")

        return cls(name, version, build_tag, python_tag, abi_tag, platform_tag)


class SourceFilename(Filename):
    def __init__(self, name: str, version: str, strict: bool = True) -> None:
        # Store the values that were originally passed for use externally
        self.original_name = name
        self.original_version = version

        filename = self._to_filename(name, version)

        # Check that the name is normalized
        if not is_normalized_name(canonicalize_name(name)):
            raise InvalidSdistFilename(
                f"Invalid filename (invalid project name {name!r}): {filename!r}"
            )
        self.name = canonicalize_name(name).replace("-", "_")
        # PEP 625: The name must only contain underscores
        if strict and self.original_name != self.name:
            raise InvalidSdistFilename(
                f"Invalid filename (non-normalized project name {name!r}): {filename!r}"
            )

        # Check that the version is valid
        try:
            self.version = Version(version)
        except InvalidVersion as e:
            raise InvalidSdistFilename(
                f"Invalid filename (invalid version {version!r}): {filename!r}"
            ) from e
        # Check that the version is normalized
        if strict and version != str(self.version):
            raise InvalidSdistFilename(
                f"Invalid filename (non-normalized version {version!r}): {filename!r}"
            )

    def _to_filename(self, name: str, version: str | Version) -> str:
        return f"{ name }-{ version }.tar.gz"

    def __str__(self) -> str:
        return self._to_filename(self.name, self.version)

    @classmethod
    def from_filename(cls, filename: str) -> SourceFilename:
        # PEP 625: Source distributions must end with .tar.gz
        if not filename.endswith(".tar.gz"):
            raise InvalidSdistFilename(
                f"Invalid filename (extension must be '.tar.gz'): {filename!r}"
            )

        # PEP 625: Source distributions may only have one hyphen, separating
        # the name and version
        if filename.count("-") > 1:
            raise InvalidSdistFilename(
                "Invalid filename (name and version parts can not contain hyphens): "
                f"{filename!r}"
            )

        if filename.count("-") == 0:
            raise InvalidSdistFilename(
                "Invalid filename (hyphen must separate name and version parts): "
                f"{filename!r}"
            )

        # Split the filename into name & version
        name, version = filename[: -len(".tar.gz")].split("-")

        return cls(name, version)
