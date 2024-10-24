# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import copy
import dataclasses
import email.message
import email.policy
import email.utils
import os
import os.path
import pathlib
import typing
import warnings

from . import markers, specifiers, utils
from . import metadata as packaging_metadata
from . import version as packaging_version
from ._pyproject import License, PyProjectReader, Readme
from .errors import ConfigurationError, ConfigurationWarning, ErrorCollector

if typing.TYPE_CHECKING:  # pragma: no cover
    import sys
    from collections.abc import Mapping, Sequence
    from typing import Any

    from .requirements import Requirement

    if sys.version_info < (3, 11):
        from typing_extensions import Self
    else:
        from typing import Self

    from .project_table import Dynamic, PyProjectTable

__all__ = [
    "ConfigurationError",
    "License",
    "Readme",
    "StandardMetadata",
    "extras_build_system",
    "extras_project",
    "extras_top_level",
]

KNOWN_TOPLEVEL_FIELDS = {"build-system", "project", "tool", "dependency-groups"}
KNOWN_BUILD_SYSTEM_FIELDS = {"backend-path", "build-backend", "requires"}
KNOWN_PROJECT_FIELDS = {
    "authors",
    "classifiers",
    "dependencies",
    "description",
    "dynamic",
    "entry-points",
    "gui-scripts",
    "keywords",
    "license",
    "license-files",
    "maintainers",
    "name",
    "optional-dependencies",
    "readme",
    "requires-python",
    "scripts",
    "urls",
    "version",
}
PRE_SPDX_METADATA_VERSIONS = {"2.1", "2.2", "2.3"}


def extras_top_level(pyproject_table: Mapping[str, Any]) -> set[str]:
    """
    Return any extra keys in the top-level of the pyproject table.
    """
    return set(pyproject_table) - KNOWN_TOPLEVEL_FIELDS


def extras_build_system(pyproject_table: Mapping[str, Any]) -> set[str]:
    """
    Return any extra keys in the build-system table.
    """
    return set(pyproject_table.get("build-system", [])) - KNOWN_BUILD_SYSTEM_FIELDS


def extras_project(pyproject_table: Mapping[str, Any]) -> set[str]:
    """
    Return any extra keys in the project table.
    """
    return set(pyproject_table.get("project", [])) - KNOWN_PROJECT_FIELDS


@dataclasses.dataclass
class StandardMetadata:
    """
    This class represents the standard metadata fields for a project. It can be
    used to read metadata from a pyproject.toml table, validate it, and write it
    to an RFC822 message or JSON.
    """

    name: str
    version: packaging_version.Version | None = None
    description: str | None = None
    license: License | str | None = None
    license_files: list[pathlib.Path] | None = None
    readme: Readme | None = None
    requires_python: specifiers.SpecifierSet | None = None
    dependencies: list[Requirement] = dataclasses.field(default_factory=list)
    optional_dependencies: dict[str, list[Requirement]] = dataclasses.field(
        default_factory=dict
    )
    entrypoints: dict[str, dict[str, str]] = dataclasses.field(default_factory=dict)
    authors: list[tuple[str, str | None]] = dataclasses.field(default_factory=list)
    maintainers: list[tuple[str, str | None]] = dataclasses.field(default_factory=list)
    urls: dict[str, str] = dataclasses.field(default_factory=dict)
    classifiers: list[str] = dataclasses.field(default_factory=list)
    keywords: list[str] = dataclasses.field(default_factory=list)
    scripts: dict[str, str] = dataclasses.field(default_factory=dict)
    gui_scripts: dict[str, str] = dataclasses.field(default_factory=dict)
    dynamic: list[Dynamic] = dataclasses.field(default_factory=list)
    """
    This field is used to track dynamic fields. You can't set a field not in this list.
    """

    def __post_init__(self) -> None:
        self.validate()

    @property
    def canonical_name(self) -> str:
        """
        Return the canonical name of the project.
        """
        return utils.canonicalize_name(self.name)

    @classmethod
    def from_pyproject(
        cls,
        data: Mapping[str, Any],
        project_dir: str | os.PathLike[str] = os.path.curdir,
    ) -> Self:
        """
        Read metadata from a pyproject.toml table. This is the main method for
        creating an instance of this class. It also supports two additional
        fields: ``allow_extra_keys`` to control what happens when extra keys are
        present in the pyproject table, and ``all_errors``, to raise all errors
        in an ExceptionGroup instead of raising the first one.
        """
        pyproject = PyProjectReader()

        pyproject_table: PyProjectTable = data  # type: ignore[assignment]
        if "project" not in pyproject_table:
            msg = "Section {key} missing in pyproject.toml"
            pyproject.config_error(msg, key="project")
            pyproject.finalize("Failed to parse pyproject.toml")
            msg = "Unreachable code"  # pragma: no cover
            raise AssertionError(msg)  # pragma: no cover

        project = pyproject_table["project"]
        project_dir = pathlib.Path(project_dir)

        extra_keys = extras_project(data)
        if extra_keys:
            extra_keys_str = ", ".join(sorted(f"{k!r}" for k in extra_keys))
            msg = "Extra keys present in {key}: {extra_keys}"
            pyproject.config_error(
                msg,
                key="project",
                extra_keys=extra_keys_str,
            )

        dynamic = pyproject.get_dynamic(project)

        for field in dynamic:
            if field in data["project"]:
                msg = (
                    'Field {key} declared as dynamic in "project.dynamic"'
                    " but is defined"
                )
                pyproject.config_error(msg, key=f"project.{field}")

        raw_name = project.get("name")
        name = "UNKNOWN"
        if raw_name is None:
            msg = "Field {key} missing"
            pyproject.config_error(msg, key="project.name")
        else:
            tmp_name = pyproject.ensure_str(raw_name, "project.name")
            if tmp_name is not None:
                name = tmp_name

        version: packaging_version.Version | None = packaging_version.Version("0.0.0")
        raw_version = project.get("version")
        if raw_version is not None:
            version_string = pyproject.ensure_str(raw_version, "project.version")
            if version_string is not None:
                try:
                    version = (
                        packaging_version.Version(version_string)
                        if version_string
                        else None
                    )
                except packaging_version.InvalidVersion:
                    msg = "Invalid {key} value, expecting a valid PEP 440 version"
                    pyproject.config_error(
                        msg, key="project.version", got=version_string
                    )
        elif "version" not in dynamic:
            msg = (
                "Field {key} missing and 'version' not specified in \"project.dynamic\""
            )
            pyproject.config_error(msg, key="project.version")

        # Description fills Summary, which cannot be multiline
        # However, throwing an error isn't backward compatible,
        # so leave it up to the users for now.
        project_description_raw = project.get("description")
        description = (
            pyproject.ensure_str(project_description_raw, "project.description")
            if project_description_raw is not None
            else None
        )

        requires_python_raw = project.get("requires-python")
        requires_python = None
        if requires_python_raw is not None:
            requires_python_string = pyproject.ensure_str(
                requires_python_raw, "project.requires-python"
            )
            if requires_python_string is not None:
                try:
                    requires_python = specifiers.SpecifierSet(requires_python_string)
                except specifiers.InvalidSpecifier:
                    msg = "Invalid {key} value, expecting a valid specifier set"
                    pyproject.config_error(
                        msg, key="project.requires-python", got=requires_python_string
                    )

        self = None
        with pyproject.collect():
            self = cls(
                name=name,
                version=version,
                description=description,
                license=pyproject.get_license(project, project_dir),
                license_files=pyproject.get_license_files(project, project_dir),
                readme=pyproject.get_readme(project, project_dir),
                requires_python=requires_python,
                dependencies=pyproject.get_dependencies(project),
                optional_dependencies=pyproject.get_optional_dependencies(project),
                entrypoints=pyproject.get_entrypoints(project),
                authors=pyproject.ensure_people(
                    project.get("authors", []), "project.authors"
                ),
                maintainers=pyproject.ensure_people(
                    project.get("maintainers", []), "project.maintainers"
                ),
                urls=pyproject.ensure_dict(project.get("urls", {}), "project.urls")
                or {},
                classifiers=pyproject.ensure_list(
                    project.get("classifiers", []), "project.classifiers"
                )
                or [],
                keywords=pyproject.ensure_list(
                    project.get("keywords", []), "project.keywords"
                )
                or [],
                scripts=pyproject.ensure_dict(
                    project.get("scripts", {}), "project.scripts"
                )
                or {},
                gui_scripts=pyproject.ensure_dict(
                    project.get("gui-scripts", {}), "project.gui-scripts"
                )
                or {},
                dynamic=dynamic,
            )

        pyproject.finalize("Failed to parse pyproject.toml")
        assert self is not None
        return self

    def validate_metdata(self, metadata_version: str) -> None:
        errors = ErrorCollector()

        if not self.version:
            msg = "Missing {key} field"
            errors.config_error(msg, key="project.version")

        if metadata_version not in PRE_SPDX_METADATA_VERSIONS:
            if isinstance(self.license, License):
                warnings.warn(
                    'Set "project.license" to an SPDX license expression'
                    " for metadata >= 2.4",
                    ConfigurationWarning,
                    stacklevel=2,
                )
            elif any(c.startswith("License ::") for c in self.classifiers):
                warnings.warn(
                    "'License ::' classifiers are deprecated for metadata >= 2.4"
                    ', use a SPDX license expression for "project.license" instead',
                    ConfigurationWarning,
                    stacklevel=2,
                )

        if (
            isinstance(self.license, str)
            and metadata_version in PRE_SPDX_METADATA_VERSIONS
        ):
            msg = (
                "Setting {key} to an SPDX license expression is supported"
                " only when emitting metadata version >= 2.4"
            )
            errors.config_error(msg, key="project.license")

        if (
            self.license_files is not None
            and metadata_version in PRE_SPDX_METADATA_VERSIONS
        ):
            msg = "{key} is supported only when emitting metadata version >= 2.4"
            errors.config_error(msg, key="project.license-files")

        errors.finalize("Metadata validation failed")

    def validate(self) -> None:
        """
        Validate metadata for consistency and correctness. Will also produce
        warnings if ``warn`` is given. Respects ``all_errors``. This is called
        when loading a pyproject.toml, and when making metadata. Checks:

        - ``metadata_version`` is a known version or None
        - ``name`` is a valid project name
        - ``license_files`` can't be used with classic ``license``
        - License classifiers can't be used with SPDX license
        - ``description`` is a single line (warning)
        - ``license`` is not an SPDX license expression if metadata_version
          >= 2.4 (warning)
        - License classifiers deprecated for metadata_version >= 2.4 (warning)
        - ``license`` is an SPDX license expression if metadata_version >= 2.4
        - ``license_files`` is supported only for metadata_version >= 2.4
        - ``project_url`` can't contain keys over 32 characters
        """
        errors = ErrorCollector()

        try:
            utils.canonicalize_name(self.name, validate=True)
        except utils.InvalidName:
            msg = (
                "Invalid project name {name!r}. A valid name consists only of ASCII"
                " letters and numbers, period, underscore and hyphen. It must start"
                " and end with a letter or number"
            )
            errors.config_error(msg, key="project.name", name=self.name)

        if self.license_files is not None and isinstance(self.license, License):
            msg = (
                '{key} must not be used when "project.license"'
                " is not a SPDX license expression"
            )
            errors.config_error(msg, key="project.license-files")

        if isinstance(self.license, str) and any(
            c.startswith("License ::") for c in self.classifiers
        ):
            msg = (
                "Setting {key} to an SPDX license expression is not"
                " compatible with 'License ::' classifiers"
            )
            errors.config_error(msg, key="project.license")

        if self.description and "\n" in self.description:
            msg = (
                'The one-line summary "project.description" should not contain more '
                "than one line. Readers might merge or truncate newlines."
            )
            errors.config_error(msg, key="project.description")

        for name in self.urls:
            if len(name) > 32:
                msg = "{key} names cannot be more than 32 characters long"
                errors.config_error(msg, key="project.urls", got=name)

        errors.finalize("[project] table validation failed")

    def metadata(
        self, *, metadata_version: str, dynamic_metadata: Sequence[str] = ()
    ) -> packaging_metadata.Metadata:
        """
        Return an Message with the metadata.
        """
        self.validate_metdata(metadata_version)

        assert self.version is not None
        message = packaging_metadata.RawMetadata(
            metadata_version=metadata_version, name=self.name, version=str(self.version)
        )

        # skip 'Platform'
        # skip 'Supported-Platform'
        if self.description:
            message["summary"] = self.description
        if self.keywords:
            message["keywords"] = self.keywords
        # skip 'Home-page'
        # skip 'Download-URL'
        if authors := _name_list(self.authors):
            message["author"] = authors

        if authors_email := _email_list(self.authors):
            message["author_email"] = authors_email

        if maintainers := _name_list(self.maintainers):
            message["maintainer"] = maintainers

        if maintainers_email := _email_list(self.maintainers):
            message["maintainer_email"] = maintainers_email

        if isinstance(self.license, License):
            message["license"] = self.license.text
        elif isinstance(self.license, str):
            message["license_expression"] = self.license

        if self.license_files is not None:
            license_files = [
                os.fspath(license_file.as_posix())
                for license_file in sorted(set(self.license_files))
            ]
            message["license_files"] = license_files
        elif (
            metadata_version not in PRE_SPDX_METADATA_VERSIONS
            and isinstance(self.license, License)
            and self.license.file
        ):
            message["license_files"] = [os.fspath(self.license.file.as_posix())]

        if self.classifiers:
            message["classifiers"] = self.classifiers
        # skip 'Provides-Dist'
        # skip 'Obsoletes-Dist'
        # skip 'Requires-External'
        if self.urls:
            message["project_urls"] = self.urls
        if self.requires_python:
            message["requires_python"] = str(self.requires_python)
        if self.dependencies:
            message["requires_dist"] = [str(d) for d in self.dependencies]
        for extra, requirements in self.optional_dependencies.items():
            norm_extra = extra.replace(".", "-").replace("_", "-").lower()
            message.setdefault("provides_extra", []).append(norm_extra)
            message.setdefault("requires_dist", []).extend(
                str(_build_extra_req(norm_extra, requirement))
                for requirement in requirements
            )
        if self.readme:
            if self.readme.content_type:
                message["description_content_type"] = self.readme.content_type
            message["description"] = self.readme.text
        # Core Metadata 2.2
        if metadata_version != "2.1":
            for field in dynamic_metadata:
                if field.lower() in {"name", "version", "dynamic"}:
                    msg = f"Field cannot be set as dynamic metadata: {field}"
                    raise ConfigurationError(msg)
                if field.lower() not in packaging_metadata.ALL_FIELDS:
                    msg = f"Field is not known: {field}"
                    raise ConfigurationError(msg)
            message["dynamic"] = list(dynamic_metadata)

        return packaging_metadata.Metadata.from_raw(message)


def _name_list(people: list[tuple[str, str | None]]) -> str | None:
    """
    Build a comma-separated list of names.
    """
    return ", ".join(name for name, email_ in people if not email_) or None


def _email_list(people: list[tuple[str, str | None]]) -> str | None:
    """
    Build a comma-separated list of emails.
    """
    return (
        ", ".join(
            email.utils.formataddr((name, _email)) for name, _email in people if _email
        )
        or None
    )


def _build_extra_req(
    extra: str,
    requirement: Requirement,
) -> Requirement:
    """
    Build a new requirement with an extra marker.
    """
    requirement = copy.copy(requirement)
    if requirement.marker:
        if "or" in requirement.marker._markers:
            requirement.marker = markers.Marker(
                f"({requirement.marker}) and extra == {extra!r}"
            )
        else:
            requirement.marker = markers.Marker(
                f"{requirement.marker} and extra == {extra!r}"
            )
    else:
        requirement.marker = markers.Marker(f"extra == {extra!r}")
    return requirement
