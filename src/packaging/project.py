"""Parse and validate the project metadata from a pyproject.toml file.

See https://www.python.org/dev/peps/pep-0621/, and
https://packaging.python.org/en/latest/specifications/declaring-project-metadata
"""
import re
import typing as t
from pathlib import Path

from .requirements import InvalidRequirement, Requirement
from .specifiers import InvalidSpecifier, SpecifierSet
from .version import InvalidVersion, Version, parse as parse_version

__all__ = ("parse",)


_ALLOWED_FIELDS = {
    "name",
    "version",
    "description",
    "readme",
    "requires-python",
    "license",
    "authors",
    "maintainers",
    "keywords",
    "classifiers",
    "urls",
    "scripts",
    "gui-scripts",
    "entry-points",
    "dependencies",
    "optional-dependencies",
    "dynamic",
}

_ALLOWED_DYNAMIC_FIELDS = _ALLOWED_FIELDS - {"name", "dynamic"}


DYNAMIC_KEY_TYPE = t.Literal[
    "version",
    "description",
    "readme",
    "requires-python",
    "license",
    "authors",
    "maintainers",
    "keywords",
    "classifiers",
    "urls",
    "scripts",
    "gui-scripts",
    "entry-points",
    "dependencies",
    "optional-dependencies",
]


class Author(t.TypedDict, total=False):
    """An author or maintainer."""

    name: str
    email: str


class ProjectData(t.TypedDict, total=False):
    """The validated PEP 621 project metadata from the pyproject.toml file."""

    name: str  # TODO ideally this would be t.Required[str] in py3.11
    dynamic: t.List[DYNAMIC_KEY_TYPE]
    version: Version
    description: str
    readme_text: str
    readme_content_type: str
    readme_path: Path
    license_text: str
    license_path: Path
    keywords: t.List[str]
    classifiers: t.List[str]
    urls: t.Dict[str, str]
    authors: t.List[Author]
    maintainers: t.List[Author]
    requires_python: SpecifierSet
    dependencies: t.List[Requirement]
    optional_dependencies: t.Dict[str, t.List[Requirement]]
    entry_points: t.Dict[str, t.Dict[str, str]]


class VError(t.NamedTuple):
    """A validation error."""

    key: str
    etype: t.Literal["key", "type", "value"]
    msg: str = ""


class ParseResult(t.NamedTuple):
    """The result of parsing the pyproject.toml file."""

    data: ProjectData
    errors: t.List[VError]


def parse(data: t.Dict[str, t.Any], root: Path) -> ParseResult:
    """Parse and validate the project metadata from a pyproject.toml file,
    according to PEP 621.

    :param data: The data from the pyproject.toml file.
    :param root: The folder containing the pyproject.toml file.
    """
    output: ProjectData = {"name": ""}
    errors: t.List[VError] = []

    if "project" not in data:
        errors.append(VError("project", "key", "missing"))
        return ParseResult(output, errors)

    project = data.get("project", {})
    if not isinstance(project, dict):
        errors.append(VError("project", "type", "must be a table"))
        return ParseResult(output, errors)

    # check for unknown keys
    unknown_keys = set(project.keys()) - _ALLOWED_FIELDS
    if unknown_keys:
        for key in unknown_keys:
            errors.append(VError(f"project.{key}", "key", "unknown"))

    # validate dynamic
    if "dynamic" in project:
        if not isinstance(project["dynamic"], list):
            errors.append(VError("project.dynamic", "type", "must be an array"))
        else:
            for i, item in enumerate(project["dynamic"]):
                if item not in _ALLOWED_DYNAMIC_FIELDS:
                    errors.append(
                        VError(
                            f"project.dynamic.{i}",
                            "value",
                            f"not in allowed fields: {item}",
                        )
                    )
                elif item in project:
                    errors.append(
                        VError(
                            f"project.dynamic.{i}", "value", f"static key found: {item}"
                        )
                    )
                else:
                    output["dynamic"].append(item)

    # validate name
    if "name" in project:
        name = project["name"]
        if not isinstance(name, str):
            errors.append(VError("project.name", "type", "must be a string"))
        else:
            if not name:
                errors.append(VError("project.name", "value", "must not be empty"))
            # normalize the name by PEP 503
            output["name"] = re.sub(r"[-_.]+", "-", name).lower()
    else:
        errors.append(VError("project.name", "key", "missing"))

    # validate version
    if "version" in project:
        if not isinstance(project["version"], str):
            errors.append(VError("project.version", "type", "must be a string"))
        else:
            try:
                output["version"] = parse_version(project["version"])
            except InvalidVersion as exc:
                errors.append(VError("project.version", "value", str(exc)))
    else:
        if "version" not in output.get("dynamic", []):
            errors.append(
                VError("project.version", "key", "missing and not in project.dynamic")
            )

    # validate description
    if "description" in project:
        if not isinstance(project["description"], str):
            errors.append(VError("project.description", "type", "must be a string"))
        else:
            output["description"] = project["description"]

    # validate readme
    if "readme" in project:
        _parse_readme(project["readme"], root, output, errors)

    # validate license
    if "license" in project:
        if not isinstance(project["license"], dict):
            errors.append(VError("project.license", "type", "must be a table"))
        else:
            license = project["license"]
            if "file" in license and "text" in license:
                errors.append(
                    VError(
                        "project.license", "key", "cannot have both 'file' and 'text'"
                    )
                )
            if "file" in license:
                result = _read_rel_path(license["file"], root, errors)
                if result is not None:
                    output["license_text"] = result.text
                    output["license_path"] = result.path
            elif "text" in license:
                if not isinstance(license["text"], str):
                    errors.append(
                        VError("project.license.text", "type", "must be a string")
                    )
                else:
                    output["license_text"] = license["text"]
            else:
                errors.append(
                    VError("project.license", "key", "missing 'file' or 'text'")
                )

    # validate authors and maintainers
    for authkey in ("authors", "maintainers"):
        if authkey not in project:
            continue
        if not isinstance(project[authkey], list):
            errors.append(VError(f"project.{authkey}", "type", "must be an array"))
            continue
        output[authkey] = []  # type: ignore[literal-required]
        for i, item in enumerate(project[authkey]):
            if not isinstance(item, dict):
                errors.append(
                    VError(f"project.{authkey}.{i}", "type", "must be a table")
                )
            elif "name" not in item and "email" not in item:
                errors.append(
                    VError(f"project.{authkey}.{i}", "key", "missing 'name' or 'email'")
                )
            else:
                unknown_keys = set(item.keys()) - {"name", "email"}
                for key in unknown_keys:
                    errors.append(
                        VError(f"project.{authkey}.{i}.{key}", "key", "unknown")
                    )
                output[authkey].append(  # type: ignore[literal-required]
                    {key: str(item[key]) for key in ("name", "email") if key in item}
                )

    # validate keywords and classifiers
    for pkey in ("keywords", "classifiers"):
        if pkey not in project:
            continue
        if not isinstance(project[pkey], list):
            errors.append(VError(f"project.{pkey}", "type", "must be an array"))
        else:
            output[pkey] = []  # type: ignore[literal-required]
            for i, item in enumerate(project[pkey]):
                if not isinstance(item, str):
                    errors.append(
                        VError(f"project.{pkey}.{i}", "type", "must be a string")
                    )
                else:
                    output[pkey].append(item)  # type: ignore[literal-required]

    # validate urls
    if "urls" in project:
        if not isinstance(project["urls"], dict):
            errors.append(VError("project.urls", "type", "must be a table"))
        else:
            output["urls"] = {}
            for key, value in project["urls"].items():
                if not isinstance(key, str):
                    errors.append(
                        VError(f"project.urls.{key}", "type", "key must be a string")
                    )
                    continue
                if not isinstance(value, str):
                    errors.append(
                        VError(f"project.urls.{key}", "type", "value must be a string")
                    )
                    continue
                output["urls"][key] = value

    # validate requires-python
    if "requires-python" in project:
        if not isinstance(project["requires-python"], str):
            errors.append(VError("project.requires-python", "type", "must be a string"))
        else:
            try:
                output["requires_python"] = SpecifierSet(project["requires-python"])
            except InvalidSpecifier as exc:
                errors.append(VError("project.requires-python", "value", str(exc)))

    # validate dependencies
    if "dependencies" in project:
        if not isinstance(project["dependencies"], list):
            errors.append(VError("project.dependencies", "type", "must be an array"))
        else:
            output["dependencies"] = []
            for i, item in enumerate(project["dependencies"]):
                if not isinstance(item, str):
                    errors.append(
                        VError(f"project.dependencies.{i}", "type", "must be a string")
                    )
                else:
                    try:
                        output["dependencies"].append(Requirement(item))
                    except InvalidRequirement as exc:
                        errors.append(
                            VError(
                                f"project.dependencies.{i}",
                                "value",
                                str(exc),
                            )
                        )

    # validate optional-dependencies
    if "optional-dependencies" in project:
        if not isinstance(project["optional-dependencies"], dict):
            errors.append(
                VError("project.optional-dependencies", "type", "must be a table")
            )
        else:
            output["optional_dependencies"] = {}
            for key, value in project["optional-dependencies"].items():
                if not isinstance(key, str):
                    errors.append(
                        VError(
                            f"project.optional-dependencies.{key}",
                            "type",
                            "key must be a string",
                        )
                    )
                    continue
                if not isinstance(value, list):
                    errors.append(
                        VError(
                            f"project.optional-dependencies.{key}",
                            "type",
                            "value must be an array",
                        )
                    )
                    continue
                output["optional_dependencies"][key] = []
                for i, item in enumerate(value):
                    if not isinstance(item, str):
                        errors.append(
                            VError(
                                f"project.optional-dependencies.{key}.{i}",
                                "type",
                                "must be a string",
                            )
                        )
                    else:
                        try:
                            output["optional_dependencies"][key].append(
                                Requirement(item)
                            )
                        except InvalidRequirement as exc:
                            errors.append(
                                VError(
                                    f"project.optional-dependencies.{key}.{i}",
                                    "value",
                                    str(exc),
                                )
                            )

    # validate entry-points
    if "entry-points" in project:
        if not isinstance(project["entry-points"], dict):
            errors.append(VError("project.entry-points", "type", "must be a table"))
        else:
            output["entry_points"] = {}
            for key, value in project["entry-points"].items():
                if not isinstance(key, str):
                    errors.append(
                        VError(
                            f"project.entry-points.{key}",
                            "type",
                            "key must be a string",
                        )
                    )
                    continue
                if key in {"console_scripts", "gui_scripts"}:
                    errors.append(
                        VError(f"project.entry-points.{key}", "key", "reserved")
                    )
                    continue
                if not isinstance(value, dict):
                    errors.append(
                        VError(
                            f"project.entry-points.{key}",
                            "type",
                            "value must be a table",
                        )
                    )
                    continue
                output["entry_points"][key] = {}
                for subkey, subvalue in value.items():
                    if not isinstance(subkey, str):
                        errors.append(
                            VError(
                                f"project.entry-points.{key}.{subkey}",
                                "type",
                                "key must be a string",
                            )
                        )
                        continue
                    if not isinstance(subvalue, str):
                        errors.append(
                            VError(
                                f"project.entry-points.{key}.{subkey}",
                                "type",
                                "value must be a string",
                            )
                        )
                        continue
                    output["entry_points"][key][subkey] = subvalue

    # validate scripts and gui-scripts
    for ekey, ename in (("scripts", "console_scripts"), ("gui-scripts", "gui_scripts")):
        if ekey not in project:
            continue
        if not isinstance(project[ekey], dict):
            errors.append(VError(f"project.{ekey}", "type", "must be a table"))
        else:
            output.setdefault("entry_points", {})[ename] = {}
            for key, value in project[ekey].items():
                if not isinstance(key, str):
                    errors.append(
                        VError(f"project.{ekey}.{key}", "type", "key must be a string")
                    )
                    continue
                if not isinstance(value, str):
                    errors.append(
                        VError(
                            f"project.{ekey}.{key}",
                            "type",
                            "value must be a string",
                        )
                    )
                    continue
                output["entry_points"][ename][key] = value

    return ParseResult(output, errors)


def _parse_readme(
    readme: t.Union[str, t.Dict[str, str]],
    root: Path,
    output: ProjectData,
    errors: t.List[VError],
) -> None:
    """Parse and validate the project readme.

    :param readme: The project readme.
    :param root: The path to the pyproject.toml file.
    :param errors: The list of validation errors.
    """
    if not isinstance(readme, (str, dict)):
        errors.append(VError("project.readme", "type", "must be a string or table"))
        return

    if isinstance(readme, str):
        result = _read_rel_path(readme, root, errors)
        if result is not None:
            output["readme_text"] = result.text
            content_type = _guess_readme_mimetype(result.path)
            if content_type is not None:
                output["readme_content_type"] = content_type
            output["readme_path"] = result.path
        return

    for key in set(readme.keys()) - {"text", "file", "content-type"}:
        errors.append(VError(f"project.readme.{key}", "key", "unknown"))

    if "content-type" in readme:
        if not isinstance(readme["content-type"], str):
            errors.append(
                VError("project.readme.content-type", "type", "must be a string")
            )
        else:
            output["readme_content_type"] = readme["content-type"]
    else:
        errors.append(VError("project.readme.content-type", "key", "missing"))

    if "text" in readme and "file" in readme:
        errors.append(
            VError(
                "project.readme",
                "value",
                "table must not contain both 'text' and 'file'",
            )
        )

    if "text" in readme:
        if not isinstance(readme["text"], str):
            errors.append(VError("project.readme.text", "type", "must be a string"))
        else:
            output["readme_text"] = readme["text"]
        return

    if "file" in readme:
        if not isinstance(readme["file"], str):
            errors.append(VError("project.readme.file", "type", "must be a string"))
        else:
            result = _read_rel_path(readme["file"], root, errors)
            if result is not None:
                output["readme_text"] = result.text
                output["readme_path"] = result.path
        return

    errors.append(
        VError("project.readme", "value", "table must contain either 'text' or 'file'")
    )


class FileContent(t.NamedTuple):
    """The content of a file."""

    path: Path
    text: str


def _read_rel_path(
    rel: str, root: Path, errors: t.List[VError]
) -> t.Optional[FileContent]:
    if Path(rel).is_absolute():
        errors.append(VError("project.readme", "value", "path must be relative"))
        return None
    path = root / rel
    if not path.is_file():
        errors.append(VError("project.readme", "value", f"file not found: {path}"))
        return None
    try:
        text = path.read_text("utf-8")
    except OSError as exc:
        errors.append(VError("project.readme", "value", str(exc)))
        return None
    return FileContent(path, text)


def _guess_readme_mimetype(path: Path) -> t.Optional[str]:
    """Guess the mimetype of the readme.

    :param path: The path to the file.
    """
    suffix = path.suffix.lower()
    if suffix == ".rst":
        return "text/x-rst"
    if suffix == ".md":
        return "text/markdown"
    return None
