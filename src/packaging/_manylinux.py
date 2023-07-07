import collections
import contextlib
import functools
import os
import re
import sys
import warnings
from typing import Dict, Generator, Iterator, NamedTuple, Optional, Tuple

from ._elffile import EIClass, EIData, ELFFile, EMachine

EF_ARM_ABIMASK = 0xFF000000
EF_ARM_ABI_VER5 = 0x05000000
EF_ARM_ABI_FLOAT_HARD = 0x00000400


# `os.PathLike` not a generic type until Python 3.9, so sticking with `str`
# as the type for `path` until then.
@contextlib.contextmanager
def _parse_elf(path: str) -> Generator[Optional[ELFFile], None, None]:
    try:
        with open(path, "rb") as f:
            yield ELFFile(f)
    except (OSError, TypeError, ValueError):
        yield None


def _is_linux_armhf(executable: str) -> bool:
    # hard-float ABI can be detected from the ELF header of the running
    # process
    # https://static.docs.arm.com/ihi0044/g/aaelf32.pdf
    with _parse_elf(executable) as f:
        return (
            f is not None
            and f.capacity == EIClass.C32
            and f.encoding == EIData.Lsb
            and f.machine == EMachine.Arm
            and f.flags & EF_ARM_ABIMASK == EF_ARM_ABI_VER5
            and f.flags & EF_ARM_ABI_FLOAT_HARD == EF_ARM_ABI_FLOAT_HARD
        )


def _is_linux_i686(executable: str) -> bool:
    with _parse_elf(executable) as f:
        return (
            f is not None
            and f.capacity == EIClass.C32
            and f.encoding == EIData.Lsb
            and f.machine == EMachine.I386
        )


def _have_compatible_abi(executable: str, arch: str) -> bool:
    if arch == "armv7l":
        return _is_linux_armhf(executable)
    if arch == "i686":
        return _is_linux_i686(executable)
    return arch in {"x86_64", "aarch64", "ppc64", "ppc64le", "s390x", "loongarch64"}


# If glibc ever changes its major version, we need to know what the last
# minor version was, so we can build the complete list of all versions.
# For now, guess what the highest minor version might be, assume it will
# be 50 for testing. Once this actually happens, update the dictionary
# with the actual value.
_LAST_GLIBC_MINOR: Dict[int, int] = collections.defaultdict(lambda: 50)


class _GLibCVersion(NamedTuple):
    major: int
    minor: int


def _glibc_version_string_confstr() -> Optional[str]:
    """
    Primary implementation of glibc_version_string using os.confstr.
    """
    # os.confstr is quite a bit faster than ctypes.DLL. It's also less likely
    # to be broken or missing. This strategy is used in the standard library
    # platform module.
    # https://github.com/python/cpython/blob/fcf1d003bf4f0100c/Lib/platform.py#L175-L183
    try:
        # Should be a string like "glibc 2.17".
        version_string: str = getattr(os, "confstr")("CS_GNU_LIBC_VERSION")
        assert version_string is not None
        _, version = version_string.rsplit()
    except (AssertionError, AttributeError, OSError, ValueError):
        # os.confstr() or CS_GNU_LIBC_VERSION not available (or a bad value)...
        return None
    return version


def _glibc_version_string_ctypes() -> Optional[str]:
    """
    Fallback implementation of glibc_version_string using ctypes.
    """
    try:
        import ctypes
    except ImportError:
        return None

    # ctypes.CDLL(None) internally calls dlopen(NULL), and as the dlopen
    # manpage says, "If filename is NULL, then the returned handle is for the
    # main program". This way we can let the linker do the work to figure out
    # which libc our process is actually using.
    #
    # We must also handle the special case where the executable is not a
    # dynamically linked executable. This can occur when using musl libc,
    # for example. In this situation, dlopen() will error, leading to an
    # OSError. Interestingly, at least in the case of musl, there is no
    # errno set on the OSError. The single string argument used to construct
    # OSError comes from libc itself and is therefore not portable to
    # hard code here. In any case, failure to call dlopen() means we
    # can proceed, so we bail on our attempt.
    try:
        process_namespace = ctypes.CDLL(None)
    except OSError:
        return None

    try:
        gnu_get_libc_version = process_namespace.gnu_get_libc_version
    except AttributeError:
        # Symbol doesn't exist -> therefore, we are not linked to
        # glibc.
        return None

    # Call gnu_get_libc_version, which returns a string like "2.5"
    gnu_get_libc_version.restype = ctypes.c_char_p
    version_str: str = gnu_get_libc_version()
    # py2 / py3 compatibility:
    if not isinstance(version_str, str):
        version_str = version_str.decode("ascii")

    return version_str


def _glibc_version_string() -> Optional[str]:
    """Returns glibc version string, or None if not using glibc."""
    return _glibc_version_string_confstr() or _glibc_version_string_ctypes()


def _parse_glibc_version(version_str: str) -> Tuple[int, int]:
    """Parse glibc version.

    We use a regexp instead of str.split because we want to discard any
    random junk that might come after the minor version -- this might happen
    in patched/forked versions of glibc (e.g. Linaro's version of glibc
    uses version strings like "2.20-2014.11"). See gh-3588.
    """
    m = re.match(r"(?P<major>[0-9]+)\.(?P<minor>[0-9]+)", version_str)
    if not m:
        warnings.warn(
            f"Expected glibc version with 2 components major.minor,"
            f" got: {version_str}",
            RuntimeWarning,
        )
        return -1, -1
    return int(m.group("major")), int(m.group("minor"))


@functools.lru_cache()
def _get_glibc_version() -> Tuple[int, int]:
    version_str = _glibc_version_string()
    if version_str is None:
        return (-1, -1)
    return _parse_glibc_version(version_str)


# From PEP 513, PEP 600
def _is_compatible(arch: str, version: _GLibCVersion) -> bool:
    sys_glibc = _get_glibc_version()
    if sys_glibc < version:
        return False
    # Check for presence of _manylinux module.
    try:
        import _manylinux  # noqa
    except ImportError:
        return True
    if hasattr(_manylinux, "manylinux_compatible"):
        result = _manylinux.manylinux_compatible(version[0], version[1], arch)
        if result is not None:
            return bool(result)
        return True
    if version == _GLibCVersion(2, 5):
        if hasattr(_manylinux, "manylinux1_compatible"):
            return bool(_manylinux.manylinux1_compatible)
    if version == _GLibCVersion(2, 12):
        if hasattr(_manylinux, "manylinux2010_compatible"):
            return bool(_manylinux.manylinux2010_compatible)
    if version == _GLibCVersion(2, 17):
        if hasattr(_manylinux, "manylinux2014_compatible"):
            return bool(_manylinux.manylinux2014_compatible)
    return True


_LEGACY_MANYLINUX_MAP = {
    # CentOS 7 w/ glibc 2.17 (PEP 599)
    (2, 17): "manylinux2014",
    # CentOS 6 w/ glibc 2.12 (PEP 571)
    (2, 12): "manylinux2010",
    # CentOS 5 w/ glibc 2.5 (PEP 513)
    (2, 5): "manylinux1",
}


def platform_tags(linux: str, arch: str) -> Iterator[str]:
    if not _have_compatible_abi(sys.executable, arch):
        return
    # Oldest glibc to be supported regardless of architecture is (2, 17).
    too_old_glibc2 = _GLibCVersion(2, 16)
    if arch in {"x86_64", "i686"}:
        # On x86/i686 also oldest glibc to be supported is (2, 5).
        too_old_glibc2 = _GLibCVersion(2, 4)
    current_glibc = _GLibCVersion(*_get_glibc_version())
    glibc_max_list = [current_glibc]
    # We can assume compatibility across glibc major versions.
    # https://sourceware.org/bugzilla/show_bug.cgi?id=24636
    #
    # Build a list of maximum glibc versions so that we can
    # output the canonical list of all glibc from current_glibc
    # down to too_old_glibc2, including all intermediary versions.
    for glibc_major in range(current_glibc.major - 1, 1, -1):
        glibc_minor = _LAST_GLIBC_MINOR[glibc_major]
        glibc_max_list.append(_GLibCVersion(glibc_major, glibc_minor))
    for glibc_max in glibc_max_list:
        if glibc_max.major == too_old_glibc2.major:
            min_minor = too_old_glibc2.minor
        else:
            # For other glibc major versions oldest supported is (x, 0).
            min_minor = -1
        for glibc_minor in range(glibc_max.minor, min_minor, -1):
            glibc_version = _GLibCVersion(glibc_max.major, glibc_minor)
            tag = "manylinux_{}_{}".format(*glibc_version)
            if _is_compatible(arch, glibc_version):
                yield linux.replace("linux", tag)
            # Handle the legacy manylinux1, manylinux2010, manylinux2014 tags.
            if glibc_version in _LEGACY_MANYLINUX_MAP:
                legacy_tag = _LEGACY_MANYLINUX_MAP[glibc_version]
                if _is_compatible(arch, glibc_version):
                    yield linux.replace("linux", legacy_tag)
