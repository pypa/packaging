"""PEP 656 support.

This module implements logic to detect if the currently running Python is
linked against musl, and what musl version is used.
"""

import functools
import operator
import os
import re
import shutil
import struct
import subprocess
import sys
from typing import IO, Iterator, NamedTuple, Optional, Tuple


def _read_unpacked(f: IO[bytes], fmt: str) -> Tuple[int, ...]:
    return struct.unpack(fmt, f.read(struct.calcsize(fmt)))


def _get_ld_musl_elf(f: IO[bytes]) -> Optional[str]:
    """Detect musl libc location by parsing the Python executable.

    Based on https://gist.github.com/lyssdod/f51579ae8d93c8657a5564aefc2ffbca
    """
    f.seek(0)
    try:
        ident = _read_unpacked(f, "16B")
    except struct.error:
        return None
    if ident[:4] != tuple(b"\x7fELF"):  # Invalid magic, not ELF.
        return None
    f.seek(struct.calcsize("HHI"), 1)  # Skip file type, machine, and version.

    try:
        # e_fmt: Format for program header.
        # p_fmt: Format for section header.
        # p_idx: Indexes to find p_type, p_offset, and p_filesz.
        e_fmt, p_fmt, p_idx = {
            1: ("IIIIHHH", "IIIIIIII", (0, 1, 4)),  # 32-bit.
            2: ("QQQIHHH", "IIQQQQQQ", (0, 2, 5)),  # 64-bit.
        }[ident[4]]
    except KeyError:
        return None
    else:
        p_get = operator.itemgetter(*p_idx)

    # Find the interpreter section and return its content.
    try:
        _, e_phoff, _, _, _, e_phentsize, e_phnum = _read_unpacked(f, e_fmt)
    except struct.error:
        return None
    for i in range(e_phnum + 1):
        f.seek(e_phoff + e_phentsize * i)
        try:
            p_type, p_offset, p_filesz = p_get(_read_unpacked(f, p_fmt))
        except struct.error:
            return None
        if p_type != 3:  # Not PT_INTERP.
            continue
        f.seek(p_offset)
        interpreter = os.fsdecode(f.read(p_filesz)).strip("\0")
        if "musl" not in interpreter:
            return None
        return interpreter
    return None


def _get_ld_musl_ldd(executable: str) -> Optional[str]:
    ldd = shutil.which("ldd")
    if not ldd:  # No dynamic program loader.
        return None
    proc = subprocess.run(
        [ldd, executable], stdout=subprocess.PIPE, universal_newlines=True
    )
    if proc.returncode != 0:  # Not a valid dynamic program.
        return None
    for line in proc.stdout.splitlines(keepends=False):
        path = line.lstrip().rsplit(None, 1)[0]
        if "musl" not in path:
            continue
        return path
    return None


def _get_ld_musl(executable: str) -> Optional[str]:
    try:
        with open(executable, "rb") as f:
            return _get_ld_musl_elf(f)
    except IOError:
        return _get_ld_musl_ldd(executable)


_version_pat = re.compile(r"Version (\d+)\.(\d+)")


class _MuslVersion(NamedTuple):
    major: int
    minor: int


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
    ld = _get_ld_musl(executable)
    if not ld:
        return None
    proc = subprocess.run([ld], stderr=subprocess.PIPE, universal_newlines=True)
    lines = [n for n in (n.strip() for n in proc.stderr.splitlines()) if n]
    if len(lines) < 2 or lines[0][:4] != "musl":
        return None
    m = re.match(r"Version (\d+)\.(\d+)", lines[1])
    if not m:
        return None
    return _MuslVersion(major=int(m.group(1)), minor=int(m.group(2)))


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


if __name__ == "__main__":
    import sysconfig

    plat = sysconfig.get_platform()
    assert plat.startswith("linux-"), "not linux"

    print("plat:", plat)
    print("musl:", _get_musl_version(sys.executable))
    print("tags:", end=" ")
    for t in platform_tags(re.sub(r"[.-]", "_", plat.split("-", 1)[-1])):
        print(t, end="\n      ")
