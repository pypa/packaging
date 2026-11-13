from __future__ import annotations

try:
    import ctypes
except ImportError:
    ctypes = None  # type: ignore[assignment]
import os
import pathlib
import platform
import re
import sys
import types
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Generator

import pretend
import pytest

from packaging import _manylinux, _musllinux, tags
from packaging._manylinux import (
    _get_glibc_version,
    _get_manylinux_module,
    _glibc_version_string,
    _glibc_version_string_confstr,
    _glibc_version_string_ctypes,
    _GLibCVersion,
    _is_compatible,
    _parse_elf,
    _parse_glibc_version,
)


@pytest.fixture(autouse=True)
def clear_lru_cache() -> Generator[None]:
    yield
    _get_glibc_version.cache_clear()
    _get_manylinux_module.cache_clear()


@pytest.fixture
def manylinux_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    monkeypatch.setattr(_manylinux, "_get_glibc_version", lambda *args: (2, 20))
    module_name = "_manylinux"
    module = types.ModuleType(module_name)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


@pytest.mark.parametrize("tf", [True, False])
@pytest.mark.parametrize(
    ("attribute", "glibc"), [("1", (2, 5)), ("2010", (2, 12)), ("2014", (2, 17))]
)
def test_module_declaration(
    monkeypatch: pytest.MonkeyPatch,
    manylinux_module: types.ModuleType,
    attribute: str,
    glibc: tuple[int, int],
    tf: bool,
) -> None:
    manylinux = f"manylinux{attribute}_compatible"
    monkeypatch.setattr(manylinux_module, manylinux, tf, raising=False)
    glibc_version = _GLibCVersion(glibc[0], glibc[1])
    res = _is_compatible("x86_64", glibc_version)
    assert tf is res


@pytest.mark.parametrize(
    ("attribute", "glibc"), [("1", (2, 5)), ("2010", (2, 12)), ("2014", (2, 17))]
)
def test_module_declaration_missing_attribute(
    monkeypatch: pytest.MonkeyPatch,
    manylinux_module: types.ModuleType,
    attribute: str,
    glibc: tuple[int, int],
) -> None:
    manylinux = f"manylinux{attribute}_compatible"
    monkeypatch.delattr(manylinux_module, manylinux, raising=False)
    glibc_version = _GLibCVersion(glibc[0], glibc[1])
    assert _is_compatible("x86_64", glibc_version)


@pytest.mark.parametrize(
    ("version", "compatible"), [((2, 0), True), ((2, 5), True), ((2, 10), False)]
)
def test_is_manylinux_compatible_glibc_support(
    version: tuple[int, int], compatible: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "_manylinux", None)
    monkeypatch.setattr(_manylinux, "_get_glibc_version", lambda: (2, 5))
    glibc_version = _GLibCVersion(version[0], version[1])
    assert bool(_is_compatible("any", glibc_version)) == compatible


@pytest.mark.parametrize("version_str", ["glibc-2.4.5", "2"])
def test_check_glibc_version_warning(version_str: str) -> None:
    msg = f"Expected glibc version with 2 components major.minor, got: {version_str}"
    with pytest.warns(RuntimeWarning, match=re.escape(msg)):
        _parse_glibc_version(version_str)


@pytest.mark.skipif(not ctypes, reason="requires ctypes")  # type: ignore[truthy-bool]
@pytest.mark.parametrize(
    ("version_str", "expected"),
    [
        # Be very explicit about bytes and Unicode for Python 2 testing.
        (b"2.4", "2.4"),
        ("2.4", "2.4"),
    ],
)
def test_glibc_version_string(
    version_str: str | bytes, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class LibcVersion:
        def __init__(self, version_str: str | bytes) -> None:
            self.version_str = version_str

        def __call__(self) -> str | bytes:
            return self.version_str

    class ProcessNamespace:
        def __init__(self, libc_version: LibcVersion) -> None:
            self.gnu_get_libc_version = libc_version

    process_namespace = ProcessNamespace(LibcVersion(version_str))
    monkeypatch.setattr(ctypes, "CDLL", lambda _: process_namespace)
    monkeypatch.setattr(_manylinux, "_glibc_version_string_confstr", lambda: False)

    assert _glibc_version_string() == expected

    del process_namespace.gnu_get_libc_version
    assert _glibc_version_string() is None


def test_glibc_version_string_confstr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "confstr", lambda _: "glibc 2.20", raising=False)
    assert _glibc_version_string_confstr() == "2.20"


def test_glibc_version_string_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "confstr", lambda _: None, raising=False)
    monkeypatch.setitem(sys.modules, "ctypes", None)
    assert _glibc_version_string() is None
    assert _get_glibc_version() == (-1, -1)


@pytest.mark.parametrize(
    "failure",
    [pretend.raiser(ValueError), pretend.raiser(OSError), lambda _: "XXX"],
)
def test_glibc_version_string_confstr_fail(
    monkeypatch: pytest.MonkeyPatch, failure: typing.Callable[[int], str | None]
) -> None:
    monkeypatch.setattr(os, "confstr", failure, raising=False)
    assert _glibc_version_string_confstr() is None


def test_glibc_version_string_confstr_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(os, "confstr", raising=False)
    assert _glibc_version_string_confstr() is None


def test_glibc_version_string_ctypes_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ctypes", None)
    assert _glibc_version_string_ctypes() is None


@pytest.mark.xfail(ctypes is None, reason="ctypes not available")
def test_glibc_version_string_ctypes_raise_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def patched_cdll(_name: str) -> None:
        raise OSError("Dynamic loading not supported")

    monkeypatch.setattr(ctypes, "CDLL", patched_cdll)
    assert _glibc_version_string_ctypes() is None


@pytest.mark.skipif(
    platform.system() != "Linux" or _glibc_version_string() is None,
    reason="requires a glibc-based Linux",
)
def test_is_manylinux_compatible_old() -> None:
    # Assuming no one is running this test with a version of glibc released in
    # 1997.
    assert _is_compatible("any", _GLibCVersion(2, 0))


def test_is_manylinux_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_manylinux, "_glibc_version_string", lambda: "2.4")
    assert _is_compatible("any", _GLibCVersion(2, 4))


def test_glibc_version_string_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_manylinux, "_glibc_version_string", lambda: None)
    assert not _is_compatible("any", _GLibCVersion(2, 4))


@pytest.mark.parametrize(
    "content", [None, "invalid-magic", "invalid-class", "invalid-data", "too-short"]
)
def test_parse_elf_bad_executable(content: str | None) -> None:
    path_str: str | None
    if content:
        path = pathlib.Path(__file__).parent / "manylinux" / f"hello-world-{content}"
        path_str = os.fsdecode(path)
    else:
        path_str = None
    # None is not supported in the type annotation, but it was tested before.
    with _parse_elf(path_str) as ef:  # type: ignore[arg-type]
        assert ef is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("arm-linux-gnueabihf", "arm-linux-gnueabihf"),
        ("", None),
        (None, None),
        (0, None),
    ],
)
def test_get_multiarch(
    monkeypatch: pytest.MonkeyPatch, value: object, expected: str | None
) -> None:
    monkeypatch.setattr(_manylinux.sysconfig, "get_config_var", lambda _: value)  # type: ignore[attr-defined]
    assert _manylinux._get_multiarch() == expected


@pytest.mark.parametrize(
    ("archs", "multiarch", "expected"),
    [
        (["armv7l"], "arm-linux-gnueabihf", True),
        (["armv8l", "armv7l"], "arm-linux-gnueabihf", True),
        (["armv7l"], "arm-linux-gnueabi", False),
        (["armv7l"], "arm-linux-musleabihf", False),
        (["i686"], "i386-linux-gnu", True),
        (["i686"], "x86_64-linux-gnux32", False),
        (["i686"], "i386-linux-musl", False),
        (["x86_64"], "x86_64-linux-musl", True),
        (["armv6l"], "arm-linux-gnueabihf", False),
    ],
)
def test_have_compatible_abi_multiarch(
    monkeypatch: pytest.MonkeyPatch,
    archs: list[str],
    multiarch: str,
    expected: bool,
) -> None:
    # The executable must not be read if MULTIARCH is set.
    monkeypatch.setattr(_manylinux, "_get_multiarch", lambda: multiarch)
    assert _manylinux._have_compatible_abi("does-not-exist", archs) is expected


@pytest.mark.parametrize(
    ("arch", "name", "expected"),
    [
        ("armv7l", "hello-world-armv7l-armhf", True),
        ("armv7l", "hello-world-armv7l-armel", False),
        ("i686", "hello-world-x86_64-i386", True),
        ("i686", "hello-world-x86_64-x32", False),
    ],
)
def test_have_compatible_abi_elf_fallback(
    monkeypatch: pytest.MonkeyPatch, arch: str, name: str, expected: bool
) -> None:
    monkeypatch.setattr(_manylinux, "_get_multiarch", lambda: None)
    path = pathlib.Path(__file__).parent / "manylinux" / name
    assert _manylinux._have_compatible_abi(os.fsdecode(path), [arch]) is expected


@pytest.mark.skipif(
    platform.system() != "Linux" or _glibc_version_string() is None,
    reason="requires a glibc-based Linux",
)
def test_sys_tags_glibc_host() -> None:
    # No mocks: this checks the real interpreter, including its MULTIARCH.
    assert not any(tag.platform.startswith("musllinux") for tag in tags.sys_tags())
    if platform.python_implementation() == "CPython" and sys.version_info >= (3, 13):
        assert _musllinux._is_glibc_build()
