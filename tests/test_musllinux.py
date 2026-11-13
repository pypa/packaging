from __future__ import annotations

import os
import pathlib
import subprocess
import typing

import pretend
import pytest

from packaging import _musllinux, tags
from packaging._musllinux import _get_musl_version, _MuslVersion, _parse_musl_version

if typing.TYPE_CHECKING:
    from collections.abc import Generator


class Proc(typing.NamedTuple):
    stderr: str


MUSL_AMD64 = "musl libc (x86_64)\nVersion 1.2.2\n"
MUSL_I386 = "musl libc (i386)\nVersion 1.2.1\n"
MUSL_AARCH64 = "musl libc (aarch64)\nVersion 1.1.24\n"
MUSL_INVALID = "musl libc (invalid)\n"
MUSL_UNKNOWN = "musl libc (unknown)\nVersion unknown\n"

MUSL_DIR = pathlib.Path(__file__).with_name("musllinux").resolve()

BIN_GLIBC_X86_64 = MUSL_DIR.joinpath("glibc-x86_64")
BIN_MUSL_X86_64 = MUSL_DIR.joinpath("musl-x86_64")
BIN_MUSL_I386 = MUSL_DIR.joinpath("musl-i386")
BIN_MUSL_AARCH64 = MUSL_DIR.joinpath("musl-aarch64")

LD_MUSL_X86_64 = "/lib/ld-musl-x86_64.so.1"
LD_MUSL_I386 = "/lib/ld-musl-i386.so.1"
LD_MUSL_AARCH64 = "/lib/ld-musl-aarch64.so.1"


@pytest.fixture(autouse=True)
def clear_lru_cache() -> Generator[None]:
    yield
    _get_musl_version.cache_clear()


@pytest.mark.parametrize(
    ("output", "version"),
    [
        (MUSL_AMD64, _MuslVersion(1, 2)),
        (MUSL_I386, _MuslVersion(1, 2)),
        (MUSL_AARCH64, _MuslVersion(1, 1)),
        (MUSL_INVALID, None),
        (MUSL_UNKNOWN, None),
    ],
    ids=["amd64-1.2.2", "i386-1.2.1", "aarch64-1.1.24", "invalid", "unknown"],
)
def test_parse_musl_version(output: str, version: _MuslVersion | None) -> None:
    assert _parse_musl_version(output) == version


@pytest.mark.parametrize(
    ("executable", "output", "version", "ld_musl"),
    [
        (MUSL_DIR.joinpath("does-not-exist"), "error", None, None),
        (BIN_GLIBC_X86_64, "error", None, None),
        (BIN_MUSL_X86_64, MUSL_AMD64, _MuslVersion(1, 2), LD_MUSL_X86_64),
        (BIN_MUSL_I386, MUSL_I386, _MuslVersion(1, 2), LD_MUSL_I386),
        (BIN_MUSL_AARCH64, MUSL_AARCH64, _MuslVersion(1, 1), LD_MUSL_AARCH64),
    ],
    ids=["does-not-exist", "glibc", "x86_64", "i386", "aarch64"],
)
def test_get_musl_version(
    monkeypatch: pytest.MonkeyPatch,
    executable: pathlib.Path,
    output: str,
    version: _MuslVersion | None,
    ld_musl: str | None,
) -> None:
    def mock_run(*args: object, **kwargs: object) -> Proc:
        return Proc(stderr=output)

    run_recorder = pretend.call_recorder(mock_run)
    monkeypatch.setattr(_musllinux.subprocess, "run", run_recorder)  # type: ignore[attr-defined]

    assert _get_musl_version(str(executable)) == version

    if ld_musl is not None:
        expected_calls = [
            pretend.call(
                [ld_musl],
                check=False,
                stderr=subprocess.PIPE,
                text=True,
            )
        ]
    else:
        expected_calls = []
    assert run_recorder.calls == expected_calls


@pytest.mark.parametrize(
    ("version_info", "multiarch", "expected"),
    [
        ((3, 13), "x86_64-linux-gnu", True),
        ((3, 13), "arm-linux-gnueabihf", True),
        ((3, 13), "x86_64-linux-musl", False),
        ((3, 13), "", False),
        ((3, 13), None, False),
        # MULTIARCH is not reliable for musl before Python 3.13.
        ((3, 12), "x86_64-linux-gnu", False),
    ],
)
def test_is_glibc_build(
    monkeypatch: pytest.MonkeyPatch,
    version_info: tuple[int, int],
    multiarch: str | None,
    expected: bool,
) -> None:
    monkeypatch.setattr(_musllinux.sys, "version_info", version_info)  # type: ignore[attr-defined]
    monkeypatch.setattr(_musllinux.sysconfig, "get_config_var", lambda _: multiarch)  # type: ignore[attr-defined]
    assert _musllinux._is_glibc_build() is expected


def test_platform_tags_glibc_build(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = pretend.call_recorder(lambda _: _MuslVersion(1, 2))
    monkeypatch.setattr(_musllinux, "_is_glibc_build", lambda: True)
    monkeypatch.setattr(_musllinux, "_get_musl_version", recorder)
    assert list(_musllinux.platform_tags(["x86_64"])) == []
    assert recorder.calls == []


def test_platform_tags_not_glibc_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_musllinux, "_is_glibc_build", lambda: False)
    monkeypatch.setattr(_musllinux, "_get_musl_version", lambda _: _MuslVersion(1, 1))
    assert list(_musllinux.platform_tags(["x86_64"])) == [
        "musllinux_1_1_x86_64",
        "musllinux_1_0_x86_64",
    ]


@pytest.mark.skipif(
    not os.path.exists("/etc/alpine-release"), reason="requires Alpine Linux"
)
def test_sys_tags_musl_host() -> None:
    # No mocks: this checks the real interpreter, including its MULTIARCH.
    platforms = {tag.platform for tag in tags.sys_tags()}
    assert any(p.startswith("musllinux_") for p in platforms)
    assert not any(p.startswith("manylinux") for p in platforms)
