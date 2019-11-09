# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import absolute_import

import distutils.util

try:
    from importlib.machinery import EXTENSION_SUFFIXES
except ImportError:  # pragma: no cover
    import imp

    EXTENSION_SUFFIXES = [x[0] for x in imp.get_suffixes()]
    del imp
import logging
import os
import platform
import re
import sys
import sysconfig
import warnings

from ._typing import MYPY_CHECK_RUNNING, cast

if MYPY_CHECK_RUNNING:  # pragma: no cover
    from typing import Dict, FrozenSet, Iterable, Iterator, List, Optional, Tuple, Union

    PythonVersion = Tuple[int, int]
    MacVersion = Tuple[int, int]
    GlibcVersion = Tuple[int, int]


logger = logging.getLogger(__name__)

INTERPRETER_SHORT_NAMES = {
    "python": "py",  # Generic.
    "cpython": "cp",
    "pypy": "pp",
    "ironpython": "ip",
    "jython": "jy",
}  # type: Dict[str, str]


_32_BIT_INTERPRETER = sys.maxsize <= 2 ** 32


class Tag(object):

    __slots__ = ["_interpreter", "_abi", "_platform"]

    def __init__(self, interpreter, abi, platform):
        # type: (str, str, str) -> None
        self._interpreter = interpreter.lower()
        self._abi = abi.lower()
        self._platform = platform.lower()

    @property
    def interpreter(self):
        # type: () -> str
        return self._interpreter

    @property
    def abi(self):
        # type: () -> str
        return self._abi

    @property
    def platform(self):
        # type: () -> str
        return self._platform

    def __eq__(self, other):
        # type: (object) -> bool
        if not isinstance(other, Tag):
            return NotImplemented

        return (
            (self.platform == other.platform)
            and (self.abi == other.abi)
            and (self.interpreter == other.interpreter)
        )

    def __hash__(self):
        # type: () -> int
        return hash((self._interpreter, self._abi, self._platform))

    def __str__(self):
        # type: () -> str
        return "{}-{}-{}".format(self._interpreter, self._abi, self._platform)

    def __repr__(self):
        # type: () -> str
        return "<{self} @ {self_id}>".format(self=self, self_id=id(self))


def parse_tag(tag):
    # type: (str) -> FrozenSet[Tag]
    tags = set()
    interpreters, abis, platforms = tag.split("-")
    for interpreter in interpreters.split("."):
        for abi in abis.split("."):
            for platform_ in platforms.split("."):
                tags.add(Tag(interpreter, abi, platform_))
    return frozenset(tags)


def _get_config_var(name, warn=False):
    # type: (str, bool) -> Union[int, str, None]
    value = sysconfig.get_config_var(name)
    if value is None and warn:
        logger.debug(
            "Config variable '%s' is unset, Python ABI tag may be incorrect", name
        )
    return value


def _normalize_string(string):
    # type: (str) -> str
    return string.replace(".", "_").replace("-", "_")


def _cpython_interpreter(py_version):
    # type: (PythonVersion) -> str
    # TODO: Is using py_version_nodot for interpreter version critical?
    return "cp{major}{minor}".format(major=py_version[0], minor=py_version[1])


def _cpython_abis(py_version, warn=False):
    # type: (PythonVersion, bool) -> List[str]
    abis = []
    version = "{}{}".format(*py_version[:2])
    debug = pymalloc = ucs4 = ""
    with_debug = _get_config_var("Py_DEBUG", warn)
    has_refcount = hasattr(sys, "gettotalrefcount")
    # Windows doesn't set Py_DEBUG, so checking for support of debug-compiled
    # extension modules is the best option.
    # https://github.com/pypa/pip/issues/3383#issuecomment-173267692
    has_ext = "_d.pyd" in EXTENSION_SUFFIXES
    if with_debug or (with_debug is None and (has_refcount or has_ext)):
        debug = "d"
    if py_version < (3, 8):
        with_pymalloc = _get_config_var("WITH_PYMALLOC", warn)
        if with_pymalloc or with_pymalloc is None:
            pymalloc = "m"
        if py_version < (3, 3):
            unicode_size = _get_config_var("Py_UNICODE_SIZE", warn)
            if unicode_size == 4 or (
                unicode_size is None and sys.maxunicode == 0x10FFFF
            ):
                ucs4 = "u"
    elif debug:
        # Debug builds can also load "normal" extension modules.
        # We can also assume no UCS-4 or pymalloc requirement.
        abis.append("cp{version}".format(version=version))
    abis.insert(
        0,
        "cp{version}{debug}{pymalloc}{ucs4}".format(
            version=version, debug=debug, pymalloc=pymalloc, ucs4=ucs4
        ),
    )
    return abis


def _cpython_tags(py_version, interpreter, abis, platforms):
    # type: (PythonVersion, str, Iterable[str], Iterable[str]) -> Iterator[Tag]
    for abi in abis:
        for platform_ in platforms:
            yield Tag(interpreter, abi, platform_)
    for tag in (Tag(interpreter, "abi3", platform_) for platform_ in platforms):
        yield tag
    for tag in (Tag(interpreter, "none", platform_) for platform_ in platforms):
        yield tag
    # PEP 384 was first implemented in Python 3.2.
    for minor_version in range(py_version[1] - 1, 1, -1):
        for platform_ in platforms:
            interpreter = "cp{major}{minor}".format(
                major=py_version[0], minor=minor_version
            )
            yield Tag(interpreter, "abi3", platform_)


def _pypy_interpreter():
    # type: () -> str
    # Ignoring sys.pypy_version_info for type checking due to typeshed lacking
    # the reference to the attribute.
    return "pp{py_major}{pypy_major}{pypy_minor}".format(
        py_major=sys.version_info[0],
        pypy_major=sys.pypy_version_info.major,  # type: ignore
        pypy_minor=sys.pypy_version_info.minor,  # type: ignore
    )


def _generic_abi():
    # type: () -> str
    abi = sysconfig.get_config_var("SOABI")
    if abi:
        return _normalize_string(abi)
    else:
        return "none"


def _pypy_tags(py_version, interpreter, abi, platforms):
    # type: (PythonVersion, str, str, Iterable[str]) -> Iterator[Tag]
    for tag in (Tag(interpreter, abi, platform) for platform in platforms):
        yield tag
    for tag in (Tag(interpreter, "none", platform) for platform in platforms):
        yield tag


def _generic_tags(interpreter, py_version, abi, platforms):
    # type: (str, PythonVersion, str, Iterable[str]) -> Iterator[Tag]
    for tag in (Tag(interpreter, abi, platform) for platform in platforms):
        yield tag
    if abi != "none":
        tags = (Tag(interpreter, "none", platform_) for platform_ in platforms)
        for tag in tags:
            yield tag


def _py_interpreter_range(py_version):
    # type: (PythonVersion) -> Iterator[str]
    """
    Yield Python versions in descending order.

    After the latest version, the major-only version will be yielded, and then
    all following versions up to 'end'.
    """
    yield "py{major}{minor}".format(major=py_version[0], minor=py_version[1])
    yield "py{major}".format(major=py_version[0])
    for minor in range(py_version[1] - 1, -1, -1):
        yield "py{major}{minor}".format(major=py_version[0], minor=minor)


def _independent_tags(interpreter, py_version, platforms):
    # type: (str, PythonVersion, Iterable[str]) -> Iterator[Tag]
    """
    Return the sequence of tags that are consistent across implementations.

    The tags consist of:
    - py*-none-<platform>
    - <interpreter>-none-any
    - py*-none-any
    """
    for version in _py_interpreter_range(py_version):
        for platform_ in platforms:
            yield Tag(version, "none", platform_)
    yield Tag(interpreter, "none", "any")
    for version in _py_interpreter_range(py_version):
        yield Tag(version, "none", "any")


def _mac_arch(arch, is_32bit=_32_BIT_INTERPRETER):
    # type: (str, bool) -> str
    if not is_32bit:
        return arch

    if arch.startswith("ppc"):
        return "ppc"

    return "i386"


def _mac_binary_formats(version, cpu_arch):
    # type: (MacVersion, str) -> List[str]
    formats = [cpu_arch]
    if cpu_arch == "x86_64":
        if version < (10, 4):
            return []
        formats.extend(["intel", "fat64", "fat32"])

    elif cpu_arch == "i386":
        if version < (10, 4):
            return []
        formats.extend(["intel", "fat32", "fat"])

    elif cpu_arch == "ppc64":
        # TODO: Need to care about 32-bit PPC for ppc64 through 10.2?
        if version > (10, 5) or version < (10, 4):
            return []
        formats.append("fat64")

    elif cpu_arch == "ppc":
        if version > (10, 6):
            return []
        formats.extend(["fat32", "fat"])

    formats.append("universal")
    return formats


def _mac_platforms(
    version=None,  # type: Optional[MacVersion]
    arch=None,  # type: Optional[str]
):
    # type: (...) -> List[str]
    version_str, _, cpu_arch = platform.mac_ver()  # type: ignore
    if version is None:
        version = cast("MacVersion", tuple(map(int, version_str.split(".")[:2])))
    else:
        version = version
    if arch is None:
        arch = _mac_arch(cpu_arch)
    else:
        arch = arch
    platforms = []
    for minor_version in range(version[1], -1, -1):
        compat_version = version[0], minor_version
        binary_formats = _mac_binary_formats(compat_version, arch)
        for binary_format in binary_formats:
            platforms.append(
                "macosx_{major}_{minor}_{binary_format}".format(
                    major=compat_version[0],
                    minor=compat_version[1],
                    binary_format=binary_format,
                )
            )
    return platforms


# From PEP 513.
def _is_manylinux_compatible(name, glibc_version):
    # type: (str, GlibcVersion) -> bool
    # Check for presence of _manylinux module.
    try:
        import _manylinux

        return bool(getattr(_manylinux, name + "_compatible"))
    except (ImportError, AttributeError):
        # Fall through to heuristic check below.
        pass

    return _have_compatible_glibc(*glibc_version)


def _glibc_version_string():
    # type: () -> Optional[str]
    # Returns glibc version string, or None if not using glibc.
    return _glibc_version_string_confstr() or _glibc_version_string_ctypes()


def _glibc_version_string_confstr():
    # type: () -> Optional[str]
    "Primary implementation of glibc_version_string using os.confstr."
    # os.confstr is quite a bit faster than ctypes.DLL. It's also less likely
    # to be broken or missing. This strategy is used in the standard library
    # platform module.
    # https://github.com/python/cpython/blob/fcf1d003bf4f0100c9d0921ff3d70e1127ca1b71/Lib/platform.py#L175-L183
    try:
        # os.confstr("CS_GNU_LIBC_VERSION") returns a string like "glibc 2.17".
        version_string = os.confstr("CS_GNU_LIBC_VERSION")
        assert version_string is not None
        _, version = version_string.split()
    except (AssertionError, AttributeError, OSError, ValueError):
        # os.confstr() or CS_GNU_LIBC_VERSION not available (or a bad value)...
        return None
    return version


def _glibc_version_string_ctypes():
    # type: () -> Optional[str]
    "Fallback implementation of glibc_version_string using ctypes."
    try:
        import ctypes
    except ImportError:
        return None

    # ctypes.CDLL(None) internally calls dlopen(NULL), and as the dlopen
    # manpage says, "If filename is NULL, then the returned handle is for the
    # main program". This way we can let the linker do the work to figure out
    # which libc our process is actually using.
    #
    # Note: typeshed is wrong here so we are ignoring this line.
    process_namespace = ctypes.CDLL(None)  # type: ignore
    try:
        gnu_get_libc_version = process_namespace.gnu_get_libc_version
    except AttributeError:
        # Symbol doesn't exist -> therefore, we are not linked to
        # glibc.
        return None

    # Call gnu_get_libc_version, which returns a string like "2.5"
    gnu_get_libc_version.restype = ctypes.c_char_p
    version_str = gnu_get_libc_version()  # type: str
    # py2 / py3 compatibility:
    if not isinstance(version_str, str):
        version_str = version_str.decode("ascii")

    return version_str


# Separated out from have_compatible_glibc for easier unit testing.
def _check_glibc_version(version_str, required_major, minimum_minor):
    # type: (str, int, int) -> bool
    # Parse string and check against requested version.
    #
    # We use a regexp instead of str.split because we want to discard any
    # random junk that might come after the minor version -- this might happen
    # in patched/forked versions of glibc (e.g. Linaro's version of glibc
    # uses version strings like "2.20-2014.11"). See gh-3588.
    m = re.match(r"(?P<major>[0-9]+)\.(?P<minor>[0-9]+)", version_str)
    if not m:
        warnings.warn(
            "Expected glibc version with 2 components major.minor,"
            " got: %s" % version_str,
            RuntimeWarning,
        )
        return False
    return (
        int(m.group("major")) == required_major
        and int(m.group("minor")) >= minimum_minor
    )


def _have_compatible_glibc(required_major, minimum_minor):
    # type: (int, int) -> bool
    version_str = _glibc_version_string()
    if version_str is None:
        return False
    return _check_glibc_version(version_str, required_major, minimum_minor)


def _linux_platforms(is_32bit=_32_BIT_INTERPRETER):
    # type: (bool) -> List[str]
    linux = _normalize_string(distutils.util.get_platform())
    if linux == "linux_x86_64" and is_32bit:
        linux = "linux_i686"
    manylinux_support = (
        ("manylinux2014", (2, 17)),  # CentOS 7 w/ glibc 2.17 (PEP 599)
        ("manylinux2010", (2, 12)),  # CentOS 6 w/ glibc 2.12 (PEP 571)
        ("manylinux1", (2, 5)),  # CentOS 5 w/ glibc 2.5 (PEP 513)
    )
    manylinux_support_iter = iter(manylinux_support)
    for name, glibc_version in manylinux_support_iter:
        if _is_manylinux_compatible(name, glibc_version):
            platforms = [linux.replace("linux", name)]
            break
    else:
        platforms = []
    # Support for a later manylinux implies support for an earlier version.
    platforms += [linux.replace("linux", name) for name, _ in manylinux_support_iter]
    platforms.append(linux)
    return platforms


def _generic_platforms():
    # type: () -> List[str]
    platform = _normalize_string(distutils.util.get_platform())
    return [platform]


def _interpreter_name():
    # type: () -> str
    try:
        name = sys.implementation.name
    except AttributeError:  # pragma: no cover
        # Python 2.7 compatibility.
        name = platform.python_implementation().lower()
    return INTERPRETER_SHORT_NAMES.get(name) or name


def _generic_interpreter(name, py_version, warn=False):
    # type: (str, PythonVersion, bool) -> str
    version = _get_config_var("py_version_nodot", warn)
    if not version:
        version = "".join(map(str, py_version[:2]))
    return "{name}{version}".format(name=name, version=version)


    # type: (bool) -> Iterator[Tag]
    """
    Returns the sequence of tag triples for the running interpreter.

    The order of the sequence corresponds to priority order for the
    interpreter, from most to least important.
    """
    py_version = sys.version_info[:2]
    interpreter_name = _interpreter_name()
    if platform.system() == "Darwin":
        platforms = _mac_platforms()
    elif platform.system() == "Linux":
        platforms = _linux_platforms()
    else:
        platforms = _generic_platforms()

    if interpreter_name == "cp":
        interpreter = _cpython_interpreter(py_version)
        abis = _cpython_abis(py_version, warn)
        for tag in _cpython_tags(py_version, interpreter, abis, platforms):
            yield tag
    elif interpreter_name == "pp":
        interpreter = _pypy_interpreter()
        abi = _generic_abi()
        for tag in _pypy_tags(py_version, interpreter, abi, platforms):
            yield tag
    else:
        interpreter = _generic_interpreter(interpreter_name, py_version, warn)
        abi = _generic_abi()
        for tag in _generic_tags(interpreter, py_version, abi, platforms):
            yield tag
    for tag in _independent_tags(interpreter, py_version, platforms):
        yield tag
