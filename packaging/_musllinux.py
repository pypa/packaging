"""PEP 656 support.

This module implements logic to detect if the currently running Python is
linked against musl, and what musl version is used.
"""

import functools
import re
import shutil
import subprocess
import sys
from typing import Iterator, NamedTuple, Optional


class _MuslVersion(NamedTuple):
    major: int
    minor: int


def _get_ld_musl(executable: str) -> Optional[str]:
    ldd = shutil.which("ldd")
    if not ldd:  # No dynamic program loader.
        return None
    proc = subprocess.run(
        [ldd, executable], stdout=subprocess.PIPE, universal_newlines=True
    )
    if proc.returncode != 0:  # Not a valid dynamic program.
        return None
    ld_musl_pat = re.compile(r"^.+/ld-musl-.+$")
    for line in proc.stdout.splitlines():
        m = ld_musl_pat.match(line)
        if not m:
            continue
        return m.string.strip().rsplit(None, 1)[0]
    return None  # Musl ldd path not found -- program not linked against musl.


_version_pat = re.compile(r"^Version (\d+)\.(\d+)", flags=re.MULTILINE)


@functools.lru_cache()
def _get_musl_version(executable: str) -> Optional[_MuslVersion]:
    """Detect currently-running musl runtime version.

    This is done by checking the specified executable's dynamic linking
    information, and invoking the loader to parse its output for a version
    string. If the loader is musl, the output would be something like::

        musl libc (x86_64)
        Version 1.2.2
        Dynamic Program Loader
    """
    ld_musl = _get_ld_musl(executable)
    if not ld_musl:
        return None
    proc = subprocess.run([ld_musl], stderr=subprocess.PIPE, universal_newlines=True)
    for m in _version_pat.finditer(proc.stderr):
        return _MuslVersion(major=int(m.group(1)), minor=int(m.group(2)))
    return None


def platform_tags(arch: str) -> Iterator[str]:
    """Generate musllinux tags compatible to the current platform.

    :param arch: Should be the part of platform tag after the ``linux_``
        prefix, e.g. ``x86_64``. The ``linux_`` prefix is assumed as a
        prerequisite for the current platform to be musllinux-compatible.

    :returns: An iterator of compatible musllinux tags.
    """
    sys_musl = _get_musl_version(sys.executable)
    if sys_musl is None:  # Python not dynamically linked against musl.
        return
    for minor in range(sys_musl.minor, -1, -1):
        yield f"musllinux_{sys_musl.major}_{minor}_{arch}"
