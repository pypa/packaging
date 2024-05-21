from __future__ import annotations

import os.path
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pytest import MonkeyPatch, TempPathFactory

from packaging.wheelfile import WheelError, WheelReader, WheelWriter


@pytest.fixture
def wheel_path(tmp_path: Path) -> Path:
    return tmp_path / "test-1.0-py2.py3-none-any.whl"


@pytest.mark.parametrize(
    "filename, reason",
    [
        pytest.param("test.whl", "wrong number of parts"),
        pytest.param("test-1.0.whl", "wrong number of parts"),
        pytest.param("test-1.0-py2.whl", "wrong number of parts"),
        pytest.param("test-1.0-py2-none.whl", "wrong number of parts"),
        pytest.param("test-1.0-py2-none-any", "extension must be '.whl'"),
        pytest.param(
            "test-1.0-py 2-none-any.whl",
            "bad file name",
            marks=[pytest.mark.xfail(reason="packaging does not fail this yet")],
        ),
    ],
)
def test_bad_wheel_filename(filename: str, reason: str) -> None:
    basename = os.path.splitext(filename)[0] if filename.endswith(".whl") else filename
    exc = pytest.raises(WheelError, WheelReader, filename)
    exc.match(rf"^Invalid wheel filename \({reason}\): {basename}$")


def test_missing_record(wheel_path: Path) -> None:
    with ZipFile(wheel_path, "w") as zf:
        zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')

    with pytest.raises(
        WheelError,
        match=(
            "^Cannot find a valid .dist-info directory. Is this really a wheel file\\?$"
        ),
    ):
        with WheelReader(wheel_path):
            pass


def test_unsupported_hash_algorithm(wheel_path: Path) -> None:
    with ZipFile(wheel_path, "w") as zf:
        zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
        zf.writestr(
            "test-1.0.dist-info/RECORD",
            "hello/héllö.py,sha000=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
        )

    with pytest.raises(WheelError, match="^Unsupported hash algorithm: sha000$"):
        with WheelReader(wheel_path):
            pass


@pytest.mark.parametrize(
    "algorithm, digest",
    [
        pytest.param("md5", "4J-scNa2qvSgy07rS4at-Q", id="md5"),
        pytest.param("sha1", "QjCnGu5Qucb6-vir1a6BVptvOA4", id="sha1"),
    ],
)
def test_weak_hash_algorithm(wheel_path: Path, algorithm: str, digest: str) -> None:
    hash_string = f"{algorithm}={digest}"
    with ZipFile(wheel_path, "w") as zf:
        zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
        zf.writestr("test-1.0.dist-info/RECORD", f"hello/héllö.py,{hash_string},25")

    with pytest.raises(
        WheelError,
        match=rf"^Weak hash algorithm \({algorithm}\) is not permitted by PEP 427$",
    ):
        with WheelReader(wheel_path):
            pass


@pytest.mark.parametrize(
    "algorithm, digest",
    [
        ("sha256", "bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo"),
        ("sha384", "cDXriAy_7i02kBeDkN0m2RIDz85w6pwuHkt2PZ4VmT2PQc1TZs8Ebvf6eKDFcD_S"),
        (
            "sha512",
            "kdX9CQlwNt4FfOpOKO_X0pn_v1opQuksE40SrWtMyP1NqooWVWpzCE3myZTfpy8g2azZON_"
            "iLNpWVxTwuDWqBQ",
        ),
    ],
    ids=["sha256", "sha384", "sha512"],
)
def test_validate_record(wheel_path: Path, algorithm: str, digest: str) -> None:
    hash_string = f"{algorithm}={digest}"
    with ZipFile(wheel_path, "w") as zf:
        zf.writestr("hello/héllö.py", 'print("Héllö, world!")\n')
        zf.writestr("test-1.0.dist-info/RECORD", f"hello/héllö.py,{hash_string},25")

    with WheelReader(wheel_path) as wf:
        wf.validate_record()


def test_testzip_missing_hash(wheel_path: Path) -> None:
    with ZipFile(wheel_path, "w") as zf:
        zf.writestr("hello/héllö.py", 'print("Héllö, world!")\n')
        zf.writestr("test-1.0.dist-info/RECORD", "")

    with WheelReader(wheel_path) as wf:
        exc = pytest.raises(WheelError, wf.validate_record)
        exc.match("^No hash found for file 'hello/héllö.py'$")


def test_validate_record_bad_hash(wheel_path: Path) -> None:
    with ZipFile(wheel_path, "w") as zf:
        zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
        zf.writestr(
            "test-1.0.dist-info/RECORD",
            "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
        )

    with WheelReader(wheel_path) as wf:
        exc = pytest.raises(WheelError, wf.validate_record)
        exc.match("^Hash mismatch for file 'hello/héllö.py'$")


def test_write_file(wheel_path: Path) -> None:
    with WheelWriter(wheel_path, generator="generator 1.0") as wf:
        wf.write_file("hello/héllö.py", 'print("Héllö, world!")\n')
        wf.write_file("hello/h,ll,.py", 'print("Héllö, world!")\n')

    with ZipFile(wheel_path, "r") as zf:
        infolist = zf.infolist()
        assert len(infolist) == 4
        assert infolist[0].filename == "hello/héllö.py"
        assert infolist[0].file_size == 25
        assert infolist[1].filename == "hello/h,ll,.py"
        assert infolist[1].file_size == 25
        assert infolist[2].filename == "test-1.0.dist-info/WHEEL"
        assert infolist[3].filename == "test-1.0.dist-info/RECORD"

        record = zf.read("test-1.0.dist-info/RECORD")
        assert record.decode("utf-8") == (
            "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25\n"
            '"hello/h,ll,.py",sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25\n'
            "test-1.0.dist-info/WHEEL,"
            "sha256=KzXSdMADLwiK8h1P5UAQ76v3nVuO2ZRU8e9GCHCC6Qs,103\n"
            "test-1.0.dist-info/RECORD,,\n"
        )


def test_timestamp(
    tmp_path_factory: TempPathFactory, wheel_path: Path, monkeypatch: MonkeyPatch
) -> None:
    # An environment variable can be used to influence the timestamp on
    # TarInfo objects inside the zip.  See issue #143.
    build_dir = tmp_path_factory.mktemp("build")
    for filename in ("one", "two", "three"):
        build_dir.joinpath(filename).write_text(filename + "\n")

    # The earliest date representable in TarInfos, 1980-01-01
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "315576060")

    with WheelWriter(wheel_path) as wf:
        wf.write_files_from_directory(build_dir)

    with ZipFile(wheel_path, "r") as zf:
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == ZIP_DEFLATED


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows does not support UNIX-like permissions"
)
def test_attributes(tmp_path_factory: TempPathFactory, wheel_path: Path) -> None:
    # With the change from ZipFile.write() to .writestr(), we need to manually
    # set member attributes.
    build_dir = tmp_path_factory.mktemp("build")
    files = (("foo", 0o644), ("bar", 0o755))
    for filename, mode in files:
        path = build_dir / filename
        path.write_text(filename + "\n")
        path.chmod(mode)

    with WheelWriter(wheel_path) as wf:
        wf.write_files_from_directory(build_dir)

    with ZipFile(wheel_path, "r") as zf:
        for filename, mode in files:
            info = zf.getinfo(filename)
            assert info.external_attr == (mode | 0o100000) << 16
            assert info.compress_type == ZIP_DEFLATED

        info = zf.getinfo("test-1.0.dist-info/RECORD")
        permissions = (info.external_attr >> 16) & 0o777
        assert permissions == 0o664


def test_unnormalized_wheel(tmp_path: Path) -> None:
    # Previous versions of "wheel" did not correctly normalize the names; test that we
    # can still read such wheels
    wheel_path = tmp_path / "Test_foo_bar-1.0.0-py3-none-any.whl"
    with ZipFile(wheel_path, "w") as zf:
        zf.writestr(
            "Test_foo_bar-1.0.0.dist-info/RECORD",
            "Test_foo_bar-1.0.0.dist-info/RECORD,,\n",
        )

    with WheelReader(wheel_path):
        pass
