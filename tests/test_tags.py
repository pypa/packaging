# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import collections

try:
    import ctypes
except ImportError:
    ctypes = None
import distutils.util

import os
import platform
import re
import sys
import sysconfig
import types
import warnings

import pretend
import pytest

from packaging import tags


@pytest.fixture
def example_tag():
    return tags.Tag("py3", "none", "any")


@pytest.fixture
def is_x86():
    return re.match(r"(i\d86|x86_64)", platform.machine()) is not None


@pytest.fixture
def is_64bit_os():
    return platform.architecture()[0] == "64bit"


@pytest.fixture
def mock_interpreter_name(monkeypatch):
    def mock(name):
        if hasattr(sys, "implementation") and sys.implementation.name != name.lower():
            monkeypatch.setattr(sys.implementation, "name", name.lower())
            return True
        elif platform.python_implementation() != name:
            monkeypatch.setattr(platform, "python_implementation", lambda: name)
            return True
        return False

    return mock


def test_tag_lowercasing():
    tag = tags.Tag("PY3", "None", "ANY")
    assert tag.interpreter == "py3"
    assert tag.abi == "none"
    assert tag.platform == "any"


def test_tag_equality():
    args = "py3", "none", "any"
    assert tags.Tag(*args) == tags.Tag(*args)


def test_tag_equality_fails_with_non_tag():
    assert not tags.Tag("py3", "none", "any") == "non-tag"


def test_tag_hashing(example_tag):
    tags = {example_tag}  # Should not raise TypeError.
    assert example_tag in tags


def test_tag_hash_equality(example_tag):
    equal_tag = tags.Tag("py3", "none", "any")
    assert example_tag == equal_tag
    assert example_tag.__hash__() == equal_tag.__hash__()


def test_tag_str(example_tag):
    assert str(example_tag) == "py3-none-any"


def test_tag_repr(example_tag):
    assert repr(example_tag) == "<py3-none-any @ {tag_id}>".format(
        tag_id=id(example_tag)
    )


def test_tag_attribute_access(example_tag):
    assert example_tag.interpreter == "py3"
    assert example_tag.abi == "none"
    assert example_tag.platform == "any"


def test_parse_tag_simple(example_tag):
    parsed_tags = tags.parse_tag(str(example_tag))
    assert parsed_tags == {example_tag}


def test_parse_tag_multi_interpreter(example_tag):
    expected = {example_tag, tags.Tag("py2", "none", "any")}
    given = tags.parse_tag("py2.py3-none-any")
    assert given == expected


def test_parse_tag_multi_platform():
    expected = {
        tags.Tag("cp37", "cp37m", platform)
        for platform in (
            "macosx_10_6_intel",
            "macosx_10_9_intel",
            "macosx_10_9_x86_64",
            "macosx_10_10_intel",
            "macosx_10_10_x86_64",
        )
    }
    given = tags.parse_tag(
        "cp37-cp37m-macosx_10_6_intel.macosx_10_9_intel.macosx_10_9_x86_64."
        "macosx_10_10_intel.macosx_10_10_x86_64"
    )
    assert given == expected


@pytest.mark.parametrize(
    "name,expected",
    [("CPython", "cp"), ("PyPy", "pp"), ("Jython", "jy"), ("IronPython", "ip")],
)
def test__interpreter_name_cpython(name, expected, mock_interpreter_name):
    mock_interpreter_name(name)
    assert tags._interpreter_name() == expected


@pytest.mark.parametrize(
    "arch, is_32bit, expected",
    [
        ("i386", True, "i386"),
        ("ppc", True, "ppc"),
        ("x86_64", False, "x86_64"),
        ("x86_64", True, "i386"),
        ("ppc64", False, "ppc64"),
        ("ppc64", True, "ppc"),
    ],
)
def test_macos_architectures(arch, is_32bit, expected):
    assert tags._mac_arch(arch, is_32bit=is_32bit) == expected


@pytest.mark.parametrize(
    "version,arch,expected",
    [
        ((10, 17), "x86_64", ["x86_64", "intel", "fat64", "fat32", "universal"]),
        ((10, 4), "x86_64", ["x86_64", "intel", "fat64", "fat32", "universal"]),
        ((10, 3), "x86_64", []),
        ((10, 17), "i386", ["i386", "intel", "fat32", "fat", "universal"]),
        ((10, 4), "i386", ["i386", "intel", "fat32", "fat", "universal"]),
        ((10, 3), "i386", []),
        ((10, 17), "ppc64", []),
        ((10, 6), "ppc64", []),
        ((10, 5), "ppc64", ["ppc64", "fat64", "universal"]),
        ((10, 3), "ppc64", []),
        ((10, 17), "ppc", []),
        ((10, 7), "ppc", []),
        ((10, 6), "ppc", ["ppc", "fat32", "fat", "universal"]),
        ((10, 0), "ppc", ["ppc", "fat32", "fat", "universal"]),
        ((11, 0), "riscv", ["riscv", "universal"]),
    ],
)
def test_macos_binary_formats(version, arch, expected):
    assert tags._mac_binary_formats(version, arch) == expected


def test_mac_platforms():
    platforms = list(tags.mac_platforms((10, 5), "x86_64"))
    assert platforms == [
        "macosx_10_5_x86_64",
        "macosx_10_5_intel",
        "macosx_10_5_fat64",
        "macosx_10_5_fat32",
        "macosx_10_5_universal",
        "macosx_10_4_x86_64",
        "macosx_10_4_intel",
        "macosx_10_4_fat64",
        "macosx_10_4_fat32",
        "macosx_10_4_universal",
    ]

    assert len(list(tags.mac_platforms((10, 17), "x86_64"))) == 14 * 5

    assert not list(tags.mac_platforms((10, 0), "x86_64"))


def test_macos_version_detection(monkeypatch):
    if platform.system() != "Darwin":
        monkeypatch.setattr(
            platform, "mac_ver", lambda: ("10.14", ("", "", ""), "x86_64")
        )
    version = platform.mac_ver()[0].split(".")
    expected = "macosx_{major}_{minor}".format(major=version[0], minor=version[1])
    platforms = list(tags.mac_platforms(arch="x86_64"))
    assert platforms[0].startswith(expected)


@pytest.mark.parametrize("arch", ["x86_64", "i386"])
def test_macos_arch_detection(arch, monkeypatch):
    if platform.system() != "Darwin" or platform.mac_ver()[2] != arch:
        monkeypatch.setattr(platform, "mac_ver", lambda: ("10.14", ("", "", ""), arch))
        monkeypatch.setattr(tags, "_mac_arch", lambda *args: arch)
    assert next(tags.mac_platforms((10, 14))).endswith(arch)


@pytest.mark.parametrize(
    "py_debug,gettotalrefcount,result",
    [(1, False, True), (0, False, False), (None, True, True)],
)
def test_cpython_abis_debug(py_debug, gettotalrefcount, result, monkeypatch):
    config = {"Py_DEBUG": py_debug, "WITH_PYMALLOC": 0, "Py_UNICODE_SIZE": 2}
    monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
    if gettotalrefcount:
        monkeypatch.setattr(sys, "gettotalrefcount", 1, raising=False)
    expected = ["cp37d" if result else "cp37"]
    assert tags._cpython_abis((3, 7)) == expected


def test_cpython_abis_debug_file_extension(monkeypatch):
    config = {"Py_DEBUG": None}
    monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
    monkeypatch.delattr(sys, "gettotalrefcount", raising=False)
    monkeypatch.setattr(tags, "EXTENSION_SUFFIXES", {"_d.pyd"})
    assert tags._cpython_abis((3, 8)) == ["cp38d", "cp38"]


@pytest.mark.parametrize(
    "debug,expected", [(True, ["cp38d", "cp38"]), (False, ["cp38"])]
)
def test_cpython_abis_debug_38(debug, expected, monkeypatch):
    config = {"Py_DEBUG": debug}
    monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
    assert tags._cpython_abis((3, 8)) == expected


@pytest.mark.parametrize(
    "pymalloc,version,result",
    [(1, (3, 7), True), (0, (3, 7), False), (None, (3, 7), True), (1, (3, 8), False)],
)
def test_cpython_abis_pymalloc(pymalloc, version, result, monkeypatch):
    config = {"Py_DEBUG": 0, "WITH_PYMALLOC": pymalloc, "Py_UNICODE_SIZE": 2}
    monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
    base_abi = "cp{}{}".format(version[0], version[1])
    expected = [base_abi + "m" if result else base_abi]
    assert tags._cpython_abis(version) == expected


@pytest.mark.parametrize(
    "unicode_size,maxunicode,version,result",
    [
        (4, 0x10FFFF, (3, 2), True),
        (2, 0xFFFF, (3, 2), False),
        (None, 0x10FFFF, (3, 2), True),
        (None, 0xFFFF, (3, 2), False),
        (4, 0x10FFFF, (3, 3), False),
    ],
)
def test_cpython_abis_wide_unicode(
    unicode_size, maxunicode, version, result, monkeypatch
):
    config = {"Py_DEBUG": 0, "WITH_PYMALLOC": 0, "Py_UNICODE_SIZE": unicode_size}
    monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
    monkeypatch.setattr(sys, "maxunicode", maxunicode)
    base_abi = "cp{}{}".format(version[0], version[1])
    expected = [base_abi + "u" if result else base_abi]
    assert tags._cpython_abis(version) == expected


def test_sys_tags_on_mac_cpython(mock_interpreter_name, monkeypatch):
    if mock_interpreter_name("CPython"):
        monkeypatch.setattr(tags, "_cpython_abis", lambda *a: ["cp33m"])
    if platform.system() != "Darwin":
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        monkeypatch.setattr(tags, "mac_platforms", lambda: ["macosx_10_5_x86_64"])
    abis = tags._cpython_abis(sys.version_info[:2])
    platforms = list(tags.mac_platforms())
    result = list(tags.sys_tags())
    assert len(abis) == 1
    assert result[0] == tags.Tag(
        "cp{major}{minor}".format(major=sys.version_info[0], minor=sys.version_info[1]),
        abis[0],
        platforms[0],
    )
    assert result[-1] == tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")


def test_generic_abi(monkeypatch):
    abi = sysconfig.get_config_var("SOABI")
    if abi:
        abi = abi.replace(".", "_").replace("-", "_")
    else:
        abi = "none"
    assert abi == tags._generic_abi()

    monkeypatch.setattr(sysconfig, "get_config_var", lambda key: "cpython-37m-darwin")
    assert tags._generic_abi() == "cpython_37m_darwin"

    monkeypatch.setattr(sysconfig, "get_config_var", lambda key: None)
    assert tags._generic_abi() == "none"


def test_pypy_interpreter(monkeypatch):
    if hasattr(sys, "pypy_version_info"):
        major, minor = sys.pypy_version_info[:2]
    else:
        attributes = ["major", "minor", "micro", "releaselevel", "serial"]
        PyPyVersion = collections.namedtuple("version_info", attributes)
        major, minor = 6, 0
        pypy_version = PyPyVersion(
            major=major, minor=minor, micro=1, releaselevel="final", serial=0
        )
        monkeypatch.setattr(sys, "pypy_version_info", pypy_version, raising=False)
    expected = "pp{}{}{}".format(sys.version_info[0], major, minor)
    assert expected == tags._pypy_interpreter()


def test_sys_tags_on_mac_pypy(mock_interpreter_name, monkeypatch):
    if mock_interpreter_name("PyPy"):
        monkeypatch.setattr(tags, "_pypy_interpreter", lambda: "pp360")
    if platform.system() != "Darwin":
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        monkeypatch.setattr(tags, "mac_platforms", lambda: ["macosx_10_5_x86_64"])
    interpreter = tags._pypy_interpreter()
    abi = tags._generic_abi()
    platforms = list(tags.mac_platforms())
    result = list(tags.sys_tags())
    assert result[0] == tags.Tag(interpreter, abi, platforms[0])
    assert result[-1] == tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")


def test_generic_platforms():
    platform = distutils.util.get_platform().replace("-", "_")
    platform = platform.replace(".", "_")
    assert list(tags._generic_platforms()) == [platform]


def test_sys_tags_on_windows_cpython(mock_interpreter_name, monkeypatch):
    if mock_interpreter_name("CPython"):
        monkeypatch.setattr(tags, "_cpython_abis", lambda *a: ["cp33m"])
    if platform.system() != "Windows":
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        monkeypatch.setattr(tags, "_generic_platforms", lambda: ["win_amd64"])
    abis = tags._cpython_abis(sys.version_info[:2])
    platforms = tags._generic_platforms()
    result = list(tags.sys_tags())
    interpreter = "cp{major}{minor}".format(
        major=sys.version_info[0], minor=sys.version_info[1]
    )
    assert len(abis) == 1
    expected = tags.Tag(interpreter, abis[0], platforms[0])
    assert result[0] == expected
    expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
    assert result[-1] == expected


def test_is_manylinux_compatible_module_support(monkeypatch):
    monkeypatch.setattr(tags, "_have_compatible_glibc", lambda *args: False)
    module_name = "_manylinux"
    module = types.ModuleType(module_name)
    module.manylinux1_compatible = True
    monkeypatch.setitem(sys.modules, module_name, module)
    assert tags._is_manylinux_compatible("manylinux1", (2, 5))
    module.manylinux1_compatible = False
    assert not tags._is_manylinux_compatible("manylinux1", (2, 5))
    del module.manylinux1_compatible
    assert not tags._is_manylinux_compatible("manylinux1", (2, 5))
    monkeypatch.setitem(sys.modules, module_name, None)
    assert not tags._is_manylinux_compatible("manylinux1", (2, 5))


def test_is_manylinux_compatible_glibc_support(monkeypatch):
    monkeypatch.setitem(sys.modules, "_manylinux", None)
    monkeypatch.setattr(
        tags, "_have_compatible_glibc", lambda major, minor: (major, minor) <= (2, 5)
    )
    assert tags._is_manylinux_compatible("manylinux1", (2, 0))
    assert tags._is_manylinux_compatible("manylinux1", (2, 5))
    assert not tags._is_manylinux_compatible("manylinux1", (2, 10))


@pytest.mark.parametrize(
    "version_str,major,minor,expected",
    [
        ("2.4", 2, 4, True),
        ("2.4", 2, 5, False),
        ("2.4", 2, 3, True),
        ("3.4", 2, 4, False),
    ],
)
def test_check_glibc_version(version_str, major, minor, expected):
    assert expected == tags._check_glibc_version(version_str, major, minor)


@pytest.mark.parametrize("version_str", ["glibc-2.4.5", "2"])
def test_check_glibc_version_warning(version_str):
    with warnings.catch_warnings(record=True) as w:
        tags._check_glibc_version(version_str, 2, 4)
        assert len(w) == 1
        assert issubclass(w[0].category, RuntimeWarning)


@pytest.mark.skipif(not ctypes, reason="requires ctypes")
@pytest.mark.parametrize(
    "version_str,expected",
    [
        # Be very explicit about bytes and Unicode for Python 2 testing.
        (b"2.4", "2.4"),
        (u"2.4", "2.4"),
    ],
)
def test_glibc_version_string(version_str, expected, monkeypatch):
    class LibcVersion:
        def __init__(self, version_str):
            self.version_str = version_str

        def __call__(self):
            return version_str

    class ProcessNamespace:
        def __init__(self, libc_version):
            self.gnu_get_libc_version = libc_version

    process_namespace = ProcessNamespace(LibcVersion(version_str))
    monkeypatch.setattr(ctypes, "CDLL", lambda _: process_namespace)
    monkeypatch.setattr(tags, "_glibc_version_string_confstr", lambda: False)

    assert tags._glibc_version_string() == expected

    del process_namespace.gnu_get_libc_version
    assert tags._glibc_version_string() is None


def test_glibc_version_string_confstr(monkeypatch):
    monkeypatch.setattr(os, "confstr", lambda x: "glibc 2.20", raising=False)
    assert tags._glibc_version_string_confstr() == "2.20"


@pytest.mark.parametrize(
    "failure", [pretend.raiser(ValueError), pretend.raiser(OSError), lambda x: "XXX"]
)
def test_glibc_version_string_confstr_fail(monkeypatch, failure):
    monkeypatch.setattr(os, "confstr", failure, raising=False)
    assert tags._glibc_version_string_confstr() is None


def test_glibc_version_string_confstr_missing(monkeypatch):
    monkeypatch.delattr(os, "confstr", raising=False)
    assert tags._glibc_version_string_confstr() is None


def test_glibc_version_string_ctypes_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "ctypes", None)
    assert tags._glibc_version_string_ctypes() is None


def test_get_config_var_does_not_log(monkeypatch):
    debug = pretend.call_recorder(lambda *a: None)
    monkeypatch.setattr(tags.logger, "debug", debug)
    tags._get_config_var("missing")
    assert debug.calls == []


def test_get_config_var_does_log(monkeypatch):
    debug = pretend.call_recorder(lambda *a: None)
    monkeypatch.setattr(tags.logger, "debug", debug)
    tags._get_config_var("missing", warn=True)
    assert debug.calls == [
        pretend.call(
            "Config variable '%s' is unset, Python ABI tag may be incorrect", "missing"
        )
    ]


def test_have_compatible_glibc(monkeypatch):
    if platform.system() == "Linux":
        # Assuming no one is running this test with a version of glibc released in
        # 1997.
        assert tags._have_compatible_glibc(2, 0)
    else:
        monkeypatch.setattr(tags, "_glibc_version_string", lambda: "2.4")
        assert tags._have_compatible_glibc(2, 4)
    monkeypatch.setattr(tags, "_glibc_version_string", lambda: None)
    assert not tags._have_compatible_glibc(2, 4)


def test_linux_platforms_64bit_on_64bit_os(is_64bit_os, is_x86, monkeypatch):
    if platform.system() != "Linux" or not is_64bit_os or not is_x86:
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
        monkeypatch.setattr(tags, "_is_manylinux_compatible", lambda *args: False)
    linux_platform = list(tags._linux_platforms(is_32bit=False))[-1]
    assert linux_platform == "linux_x86_64"


def test_linux_platforms_32bit_on_64bit_os(is_64bit_os, is_x86, monkeypatch):
    if platform.system() != "Linux" or not is_64bit_os or not is_x86:
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
        monkeypatch.setattr(tags, "_is_manylinux_compatible", lambda *args: False)
    linux_platform = list(tags._linux_platforms(is_32bit=True))[-1]
    assert linux_platform == "linux_i686"


def test_linux_platforms_manylinux_unsupported(monkeypatch):
    monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
    monkeypatch.setattr(tags, "_is_manylinux_compatible", lambda *args: False)
    linux_platform = list(tags._linux_platforms(is_32bit=False))
    assert linux_platform == ["linux_x86_64"]


def test_linux_platforms_manylinux1(monkeypatch):
    monkeypatch.setattr(
        tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux1"
    )
    if platform.system() != "Linux":
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
    platforms = list(tags._linux_platforms(is_32bit=False))
    assert platforms == ["manylinux1_x86_64", "linux_x86_64"]


def test_linux_platforms_manylinux2010(monkeypatch):
    monkeypatch.setattr(
        tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux2010"
    )
    if platform.system() != "Linux":
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
    platforms = list(tags._linux_platforms(is_32bit=False))
    expected = ["manylinux2010_x86_64", "manylinux1_x86_64", "linux_x86_64"]
    assert platforms == expected


def test_linux_platforms_manylinux2014(monkeypatch):
    monkeypatch.setattr(
        tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux2014"
    )
    if platform.system() != "Linux":
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
    platforms = list(tags._linux_platforms(is_32bit=False))
    expected = [
        "manylinux2014_x86_64",
        "manylinux2010_x86_64",
        "manylinux1_x86_64",
        "linux_x86_64",
    ]
    assert platforms == expected


def test_sys_tags_linux_cpython(mock_interpreter_name, monkeypatch):
    if mock_interpreter_name("CPython"):
        monkeypatch.setattr(tags, "_cpython_abis", lambda *a: ["cp33m"])
    if platform.system() != "Linux":
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(tags, "_linux_platforms", lambda: ["linux_x86_64"])
    abis = list(tags._cpython_abis(sys.version_info[:2]))
    platforms = list(tags._linux_platforms())
    result = list(tags.sys_tags())
    expected_interpreter = "cp{major}{minor}".format(
        major=sys.version_info[0], minor=sys.version_info[1]
    )
    assert len(abis) == 1
    assert result[0] == tags.Tag(expected_interpreter, abis[0], platforms[0])
    expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
    assert result[-1] == expected


def test_generic_sys_tags(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Generic")
    monkeypatch.setattr(tags, "_interpreter_name", lambda: "generic")

    result = list(tags.sys_tags())
    expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
    assert result[-1] == expected


def test_warn_keyword_parameters():
    assert not tags._warn_keyword_parameter("test_warn_keyword_parameters", {})
    assert not tags._warn_keyword_parameter(
        "test_warn_keyword_parameters", {"warn": False}
    )
    assert tags._warn_keyword_parameter("test_warn_keyword_parameters", {"warn": True})
    message_re = re.compile(r"too_many.+{!r}".format("whatever"))
    with pytest.raises(TypeError, match=message_re):
        tags._warn_keyword_parameter("too_many", {"warn": True, "whatever": True})
    message_re = re.compile(r"missing.+{!r}".format("unexpected"))
    with pytest.raises(TypeError, match=message_re):
        tags._warn_keyword_parameter("missing", {"unexpected": True})


def test_cpython_tags_all_args():
    result = list(tags.cpython_tags((3, 8), ["cp38d", "cp38"], ["plat1", "plat2"]))
    assert result == [
        tags.Tag("cp38", "cp38d", "plat1"),
        tags.Tag("cp38", "cp38d", "plat2"),
        tags.Tag("cp38", "cp38", "plat1"),
        tags.Tag("cp38", "cp38", "plat2"),
        tags.Tag("cp38", "abi3", "plat1"),
        tags.Tag("cp38", "abi3", "plat2"),
        tags.Tag("cp38", "none", "plat1"),
        tags.Tag("cp38", "none", "plat2"),
        tags.Tag("cp37", "abi3", "plat1"),
        tags.Tag("cp37", "abi3", "plat2"),
        tags.Tag("cp36", "abi3", "plat1"),
        tags.Tag("cp36", "abi3", "plat2"),
        tags.Tag("cp35", "abi3", "plat1"),
        tags.Tag("cp35", "abi3", "plat2"),
        tags.Tag("cp34", "abi3", "plat1"),
        tags.Tag("cp34", "abi3", "plat2"),
        tags.Tag("cp33", "abi3", "plat1"),
        tags.Tag("cp33", "abi3", "plat2"),
        tags.Tag("cp32", "abi3", "plat1"),
        tags.Tag("cp32", "abi3", "plat2"),
    ]
    result = list(tags.cpython_tags((3, 3), ["cp33m"], ["plat1", "plat2"]))
    assert result == [
        tags.Tag("cp33", "cp33m", "plat1"),
        tags.Tag("cp33", "cp33m", "plat2"),
        tags.Tag("cp33", "abi3", "plat1"),
        tags.Tag("cp33", "abi3", "plat2"),
        tags.Tag("cp33", "none", "plat1"),
        tags.Tag("cp33", "none", "plat2"),
        tags.Tag("cp32", "abi3", "plat1"),
        tags.Tag("cp32", "abi3", "plat2"),
    ]


def test_cpython_tags_defaults(monkeypatch):
    # python_version
    tag = next(tags.cpython_tags(abis=["abi3"], platforms=["any"]))
    interpreter = "cp{}{}".format(*sys.version_info[:2])
    assert tag == tags.Tag(interpreter, "abi3", "any")
    # abis
    with monkeypatch.context() as m:
        m.setattr(tags, "_cpython_abis", lambda _1, _2: ["cp38"])
        result = list(tags.cpython_tags((3, 8), platforms=["any"]))
    assert tags.Tag("cp38", "cp38", "any") in result
    assert tags.Tag("cp38", "abi3", "any") in result
    assert tags.Tag("cp38", "none", "any") in result
    # platforms
    with monkeypatch.context() as m:
        m.setattr(tags, "_platform_tags", lambda: ["plat1"])
        result = list(tags.cpython_tags((3, 8), abis=["whatever"]))
    assert tags.Tag("cp38", "whatever", "plat1") in result


@pytest.mark.parametrize("abis", [["abi3"], ["none"]])
def test_cpython_tags_skip_redundant_abis(abis):
    results = list(tags.cpython_tags((3, 0), abis=abis, platforms=["any"]))
    assert results == [tags.Tag("cp30", "abi3", "any"), tags.Tag("cp30", "none", "any")]


def test_pypy_tags(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(tags, "_pypy_interpreter", lambda: "pp370")
        result = list(tags.pypy_tags(abis=["pp370"], platforms=["plat1"]))
    assert result == [
        tags.Tag("pp370", "pp370", "plat1"),
        tags.Tag("pp370", "none", "plat1"),
    ]

    with monkeypatch.context() as m:
        m.setattr(tags, "_pypy_interpreter", lambda: "pp370")
        result = list(tags.pypy_tags("pp360", ["pp360"], ["plat1"]))
    assert result == [
        tags.Tag("pp360", "pp360", "plat1"),
        tags.Tag("pp360", "none", "plat1"),
    ]


def test_generic_interpreter(monkeypatch):
    monkeypatch.setattr(sysconfig, "get_config_var", lambda key: "42")
    monkeypatch.setattr(tags, "_interpreter_name", lambda: "sillywalk")
    assert tags._generic_interpreter() == "sillywalk42"


def test_generic_interpreter_no_config_var(monkeypatch):
    monkeypatch.setattr(sysconfig, "get_config_var", lambda _: None)
    monkeypatch.setattr(tags, "_interpreter_name", lambda: "sillywalk")
    assert tags._generic_interpreter() == "sillywalk{}{}".format(*sys.version_info[:2])


def test_generic_tags():
    result = list(tags.generic_tags("sillywalk33", ["abi"], ["plat1", "plat2"]))
    assert result == [
        tags.Tag("sillywalk33", "abi", "plat1"),
        tags.Tag("sillywalk33", "abi", "plat2"),
        tags.Tag("sillywalk33", "none", "plat1"),
        tags.Tag("sillywalk33", "none", "plat2"),
    ]

    no_abi = list(tags.generic_tags("sillywalk34", ["none"], ["plat1", "plat2"]))
    assert no_abi == [
        tags.Tag("sillywalk34", "none", "plat1"),
        tags.Tag("sillywalk34", "none", "plat2"),
    ]


def test_generic_tags_defaults(monkeypatch):
    # interpreter
    with monkeypatch.context() as m:
        m.setattr(tags, "_generic_interpreter", lambda warn: "sillywalk")
        result = list(tags.generic_tags(abis=["none"], platforms=["any"]))
    assert result == [tags.Tag("sillywalk", "none", "any")]
    # abis
    with monkeypatch.context() as m:
        m.setattr(tags, "_generic_abi", lambda: "abi")
        result = list(tags.generic_tags(interpreter="sillywalk", platforms=["any"]))
    assert result == [
        tags.Tag("sillywalk", "abi", "any"),
        tags.Tag("sillywalk", "none", "any"),
    ]
    # platforms
    with monkeypatch.context() as m:
        m.setattr(tags, "_platform_tags", lambda: ["plat"])
        result = list(tags.generic_tags(interpreter="sillywalk", abis=["none"]))
    assert result == [tags.Tag("sillywalk", "none", "plat")]


def test_compatible_tags():
    result = list(tags.compatible_tags((3, 3), "cp33", ["plat1", "plat2"]))
    assert result == [
        tags.Tag("py33", "none", "plat1"),
        tags.Tag("py33", "none", "plat2"),
        tags.Tag("py3", "none", "plat1"),
        tags.Tag("py3", "none", "plat2"),
        tags.Tag("py32", "none", "plat1"),
        tags.Tag("py32", "none", "plat2"),
        tags.Tag("py31", "none", "plat1"),
        tags.Tag("py31", "none", "plat2"),
        tags.Tag("py30", "none", "plat1"),
        tags.Tag("py30", "none", "plat2"),
        tags.Tag("cp33", "none", "any"),
        tags.Tag("py33", "none", "any"),
        tags.Tag("py3", "none", "any"),
        tags.Tag("py32", "none", "any"),
        tags.Tag("py31", "none", "any"),
        tags.Tag("py30", "none", "any"),
    ]


@pytest.mark.parametrize(
    "platform_name,dispatch_func",
    [
        ("Darwin", "mac_platforms"),
        ("Linux", "_linux_platforms"),
        ("Generic", "_generic_platforms"),
    ],
)
def test__platform_tags(platform_name, dispatch_func, monkeypatch):
    expected = ["sillywalk"]
    monkeypatch.setattr(platform, "system", lambda: platform_name)
    monkeypatch.setattr(tags, dispatch_func, lambda: expected)
    assert tags._platform_tags() == expected
