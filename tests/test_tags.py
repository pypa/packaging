# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import collections
try:
    import ctypes
except ImportError:
    ctypes = None
import distutils.util
import os.path
try:
    import pathlib
except ImportError:
    pathlib = None
import platform
import sys
import sysconfig
import types
import warnings

import pytest

from packaging import tags


@pytest.fixture
def example_tag():
    return tags.Tag("py3", "none", "any")


def test_Tag_lowercasing():
    tag = tags.Tag("PY3", "None", "ANY")
    assert tag.interpreter == "py3"
    assert tag.abi == "none"
    assert tag.platform == "any"


def test_Tag_equality():
    args = "py3", "none", "any"
    assert tags.Tag(*args) == tags.Tag(*args)


def test_Tag_hashing(example_tag):
    tags = {example_tag}  # Should not raise TypeError.
    assert example_tag in tags


def test_Tag_str(example_tag):
    assert str(example_tag) == "py3-none-any"


def test_Tag_repr(example_tag):
    assert repr(example_tag) == "<py3-none-any @ {tag_id}>".format(
        tag_id=id(example_tag)
    )


def test_Tag_attribute_access(example_tag):
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


def test_parse_wheel_filename_simple(example_tag):
    given = tags.parse_wheel_filename("gidgethub-3.0.0-py3-none-any.whl")
    assert given == {example_tag}


def test_parse_wheel_filename_path(example_tag):
    path = os.path.join("some", "location", "gidgethub-3.0.0-py3-none-any.whl")
    given = tags.parse_wheel_filename(path)
    assert given == {example_tag}
    if pathlib and sys.version_info[:2] >= (3, 6):
        filename = "gidgethub-3.0.0-py3-none-any.whl"
        given = tags.parse_wheel_filename(
            pathlib.PurePath("some") / "location" / filename
        )
        assert given == {example_tag}


def test_parse_wheel_filename_multi_interpreter(example_tag):
    expected = {example_tag, tags.Tag("py2", "none", "any")}
    given = tags.parse_wheel_filename("pip-18.0-py2.py3-none-any.whl")
    assert given == expected


@pytest.mark.parametrize(
    "name,expected",
    [("CPython", "cp"), ("PyPy", "pp"), ("Jython", "jy"),
     ("IronPython", "ip")],
)
def test__interpreter_name_cpython(name, expected, monkeypatch):
    if platform.python_implementation().lower() != name:
        monkeypatch.setattr(platform, "python_implementation", lambda: name)
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
def test_macOS_architectures(arch, is_32bit, expected):
    assert tags._mac_arch(arch, is_32bit=is_32bit) == expected


@pytest.mark.parametrize(
    "version,arch,expected",
    [
        ((10, 17), "x86_64", ["x86_64", "intel", "fat64", "fat32",
                              "universal"]),
        ((10, 4), "x86_64", ["x86_64", "intel", "fat64", "fat32",
                             "universal"]),
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
        ((11, 0), "riscv", ["riscv", "universal"])
    ],
)
def test_macOS_binary_formats(version, arch, expected):
    assert tags._mac_binary_formats(version, arch) == expected


def test_mac_platforms():
    platforms = tags._mac_platforms((10, 5), "x86_64")
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

    assert len(tags._mac_platforms((10, 17), "x86_64")) == 14 * 5

    assert not tags._mac_platforms((10, 0), "x86_64")


def test_macOS_version_detection(monkeypatch):
    if platform.system() != "Darwin":
        monkeypatch.setattr(
            platform, "mac_ver", lambda: ("10.14", ("", "", ""), "x86_64")
        )
    version = platform.mac_ver()[0].split(".")
    expected = "macosx_{major}_{minor}".format(major=version[0],
                                               minor=version[1])
    platforms = tags._mac_platforms(arch="x86_64")
    assert platforms[0].startswith(expected)


@pytest.mark.parametrize("arch", ["x86_64", "i386"])
def test_macOS_arch_detection(arch, monkeypatch):
    if platform.system() != "Darwin" or platform.mac_ver()[2] != arch:
        monkeypatch.setattr(platform, "mac_ver",
                            lambda: ("10.14", ("", "", ""), arch))
    assert tags._mac_platforms((10, 14))[0].endswith(arch)


def test_cpython_abi_py3(monkeypatch):
    has_SOABI = bool(sysconfig.get_config_var("SOABI"))
    if platform.python_implementation() != "CPython" or not has_SOABI:
        monkeypatch.setattr(
            sysconfig, "get_config_var", lambda key: "'cpython-37m-darwin'"
        )
    _, soabi, _ = sysconfig.get_config_var("SOABI").split("-", 2)
    result = tags._cpython_abi(sys.version_info[:2])
    assert result == "cp{soabi}".format(soabi=soabi)


@pytest.mark.parametrize(
    "debug,pymalloc,unicode_width",
    [
        (False, False, 2),
        (True, False, 2),
        (False, True, 2),
        (False, False, 4),
        (True, True, 2),
        (False, True, 4),
        (True, True, 4),
    ],
)
def test_cpython_abi_py2(debug, pymalloc, unicode_width, monkeypatch):
    has_SOABI = sysconfig.get_config_var("SOABI")
    if platform.python_implementation() != "CPython" or has_SOABI:
        diff_debug = debug != sysconfig.get_config_var("Py_DEBUG")
        diff_malloc = pymalloc != sysconfig.get_config_var("WITH_PYMALLOC")
        unicode_size = sysconfig.get_config_var("Py_UNICODE_SIZE")
        diff_unicode_size = unicode_size != unicode_width
        if diff_debug or diff_malloc or diff_unicode_size:
            config_vars = {"SOABI": None, "Py_DEBUG": int(debug),
                           "WITH_PYMALLOC": int(pymalloc),
                           "Py_UNICODE_SIZE": unicode_width}
            monkeypatch.setattr(sysconfig, "get_config_var",
                                config_vars.__getitem__)
        options = ""
        if debug:
            options += "d"
        if pymalloc:
            options += "m"
        if unicode_width == 4:
            options += "u"
        assert "cp33{}".format(options) == tags._cpython_abi((3, 3))


def test_independent_tags():
    result = list(tags._independent_tags("cp33", (3, 3), ["plat1", "plat2"]))
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


def test_cpython_tags():
    result = list(tags._cpython_tags((3, 3), "cp33", "cp33m",
                                     ["plat1", "plat2"]))
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


def test_sys_tags_on_mac_cpython(monkeypatch):
    if platform.python_implementation() != "CPython":
        monkeypatch.setattr(platform, "python_implementation",
                            lambda: "CPython")
        monkeypatch.setattr(tags, "_cpython_abi", lambda py_version: "cp33m")
    if platform.system() != "Darwin":
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        monkeypatch.setattr(tags, "_mac_platforms",
                            lambda: ["macosx_10_5_x86_64"])
    abi = tags._cpython_abi(sys.version_info[:2])
    platforms = tags._mac_platforms()
    result = list(tags.sys_tags())
    assert result[0] == tags.Tag(
        "cp{major}{minor}".format(major=sys.version_info[0],
                                  minor=sys.version_info[1]),
        abi,
        platforms[0],
    )
    assert result[-1] == tags.Tag("py{}0".format(sys.version_info[0]), "none",
                                  "any")


def test_generic_abi(monkeypatch):
    abi = sysconfig.get_config_var("SOABI")
    if abi:
        abi = abi.replace(".", "_").replace("-", "_")
    else:
        abi = "none"
    assert abi == tags._generic_abi()
    monkeypatch.setattr(sysconfig, "get_config_var", lambda key: None)
    assert tags._generic_abi() == "none"


def test_pypy_interpreter(monkeypatch):
    if hasattr(sys, "pypy_version_info"):
            major, minor = sys.pypy_version_info[:2]
    else:
        attributes = ["major", "minor", "micro", "releaselevel", "serial"]
        PyPyVersion = collections.namedtuple("version_info", attributes)
        major, minor = 6, 0
        pypy_version = PyPyVersion(major=major, minor=minor, micro=1,
                                   releaselevel="final", serial=0)
        monkeypatch.setattr(sys, "pypy_version_info", pypy_version,
                            raising=False)
    expected = "pp{}{}{}".format(sys.version_info[0], major, minor)
    assert expected == tags._pypy_interpreter()


def test_pypy_tags(monkeypatch):
    if platform.python_implementation() != "PyPy":
        monkeypatch.setattr(platform, "python_implementation", lambda: "PyPy")
        monkeypatch.setattr(tags, "_pypy_interpreter", lambda: "pp360")
    interpreter = tags._pypy_interpreter()
    result = list(tags._pypy_tags((3, 3), interpreter, "pypy3_60",
                                  ["plat1", "plat2"]))
    assert result == [
        tags.Tag(interpreter, "pypy3_60", "plat1"),
        tags.Tag(interpreter, "pypy3_60", "plat2"),
        tags.Tag(interpreter, "none", "plat1"),
        tags.Tag(interpreter, "none", "plat2"),
    ]


def test_sys_tags_on_mac_pypy(monkeypatch):
    if platform.python_implementation() != "PyPy":
        monkeypatch.setattr(platform, "python_implementation", lambda: "PyPy")
        monkeypatch.setattr(tags, "_pypy_interpreter", lambda: "pp360")
    if platform.system() != "Darwin":
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        monkeypatch.setattr(tags, "_mac_platforms",
                            lambda: ["macosx_10_5_x86_64"])
    interpreter = tags._pypy_interpreter()
    abi = tags._generic_abi()
    platforms = tags._mac_platforms()
    result = list(tags.sys_tags())
    assert result[0] == tags.Tag(interpreter, abi, platforms[0])
    assert result[-1] == tags.Tag("py{}0".format(sys.version_info[0]), "none",
                                  "any")


def test_generic_interpreter():
    version = sysconfig.get_config_var("py_version_nodot")
    if not version:
        version = "".join(sys.version_info[:2])
    result = tags._generic_interpreter("sillywalk", sys.version_info[:2])
    assert result == "sillywalk{version}".format(version=version)


def test_generic_interpreter_no_config_var(monkeypatch):
    monkeypatch.setattr(sysconfig, "get_config_var", lambda _: None)
    assert tags._generic_interpreter("sillywalk", (3, 6)) == "sillywalk36"


def test_generic_platforms():
    platform = distutils.util.get_platform().replace("-", "_")
    platform = platform.replace(".", "_")
    assert tags._generic_platforms() == [platform]


def test_generic_tags():
    result = list(tags._generic_tags("sillywalk33", (3, 3), "abi",
                                     ["plat1", "plat2"]))
    assert result == [
        tags.Tag("sillywalk33", "abi", "plat1"),
        tags.Tag("sillywalk33", "abi", "plat2"),
        tags.Tag("sillywalk33", "none", "plat1"),
        tags.Tag("sillywalk33", "none", "plat2"),
    ]

    no_abi = tags._generic_tags("sillywalk34", (3, 4), "none", ["plat1", "plat2"])
    assert list(no_abi) == [
        tags.Tag("sillywalk34", "none", "plat1"),
        tags.Tag("sillywalk34", "none", "plat2"),
    ]


def test_sys_tags_on_windows_cpython(monkeypatch):
    if platform.python_implementation() != "CPython":
        monkeypatch.setattr(platform, "python_implementation",
                            lambda: "CPython")
        monkeypatch.setattr(tags, "_cpython_abi", lambda py_version: "cp33m")
    if platform.system() != "Windows":
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        monkeypatch.setattr(tags, "_generic_platforms",
                            lambda: ["win_amd64"])
    abi = tags._cpython_abi(sys.version_info[:2])
    platforms = tags._generic_platforms()
    result = list(tags.sys_tags())
    interpreter = "cp{major}{minor}".format(major=sys.version_info[0],
                                            minor=sys.version_info[1])
    expected = tags.Tag(interpreter, abi, platforms[0])
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
    monkeypatch.setattr(tags, "_have_compatible_glibc",
                        lambda major, minor: (major, minor) <= (2, 5))
    assert tags._is_manylinux_compatible("manylinux1", (2, 0))
    assert tags._is_manylinux_compatible("manylinux1", (2, 5))
    assert not tags._is_manylinux_compatible("manylinux1", (2, 10))


@pytest.mark.parametrize("version_str,major,minor,expected", [
    ("2.4", 2, 4, True),
    ("2.4", 2, 5, False),
    ("2.4", 2, 3, True),
    ("3.4", 2, 4, False),
])
def test_check_glibc_version(version_str, major, minor, expected):
    assert expected == tags._check_glibc_version(version_str, major, minor)


@pytest.mark.parametrize("version_str", [
    "glibc-2.4.5",
    "2",
])
def test_check_glibc_version_warning(version_str):
    with warnings.catch_warnings(record=True) as w:
        tags._check_glibc_version(version_str, 2, 4)
        assert len(w) == 1
        assert issubclass(w[0].category, RuntimeWarning)


@pytest.mark.skipif(not ctypes, reason="requires ctypes")
@pytest.mark.parametrize("version_str,expected", [
    (b"2.4", "2.4"),
    ("2.4", "2.4"),
])
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
    monkeypatch.setattr(ctypes, "CDLL",
                        lambda _: process_namespace)

    assert tags._glibc_version_string() == expected

    del process_namespace.gnu_get_libc_version
    assert tags._glibc_version_string() is None


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


def test_linux_platforms_64bit_on_64bit_OS(monkeypatch):
    is_64bit_OS = distutils.util.get_platform().endswith("_x86_64")
    if platform.system() != "Linux" or not is_64bit_OS:
        monkeypatch.setattr(distutils.util, "get_platform",
                            lambda: "linux_x86_64")
        monkeypatch.setattr(tags, "_is_manylinux_compatible",
                            lambda *args: False)
    linux_platform = tags._linux_platforms(is_32bit=False)[-1]
    assert linux_platform == "linux_x86_64"


def test_linux_platforms_32bit_on_64bit_OS(monkeypatch):
    is_64bit_OS = distutils.util.get_platform().endswith("_x86_64")
    if platform.system() != "Linux" or not is_64bit_OS:
        monkeypatch.setattr(distutils.util, "get_platform",
                            lambda: "linux_x86_64")
        monkeypatch.setattr(tags, "_is_manylinux_compatible",
                            lambda *args: False)
    linux_platform = tags._linux_platforms(is_32bit=True)[-1]
    assert linux_platform == "linux_i686"


def test_linux_platforms_manylinux1(monkeypatch):
    monkeypatch.setattr(tags, "_is_manylinux_compatible",
                        lambda name, _: name == "manylinux1")
    if platform.system() != "Linux":
        monkeypatch.setattr(distutils.util, "get_platform",
                            lambda: "linux_x86_64")
    platforms = tags._linux_platforms(is_32bit=False)
    assert platforms == ["manylinux1_x86_64", "linux_x86_64"]


def test_linux_platforms_manylinux2010(monkeypatch):
    monkeypatch.setattr(tags, "_is_manylinux_compatible",
                        lambda name, _: name == "manylinux2010")
    if platform.system() != "Linux":
        monkeypatch.setattr(distutils.util, "get_platform",
                            lambda: "linux_x86_64")
    platforms = tags._linux_platforms(is_32bit=False)
    expected = ["manylinux2010_x86_64", "manylinux1_x86_64", "linux_x86_64"]
    assert platforms == expected


def test_sys_tags_linux_cpython(monkeypatch):
    if platform.python_implementation() != "CPython":
        monkeypatch.setattr(platform, "python_implementation",
                            lambda: "CPython")
        monkeypatch.setattr(tags, "_cpython_abi", lambda py_version: "cp33m")
    if platform.system() != "Linux":
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(tags, "_linux_platforms",
                            lambda: ["linux_x86_64"])
    abi = tags._cpython_abi(sys.version_info[:2])
    platforms = tags._linux_platforms()
    result = list(tags.sys_tags())
    expected_interpreter = "cp{major}{minor}".format(major=sys.version_info[0],
                                                     minor=sys.version_info[1])
    assert result[0] == tags.Tag(expected_interpreter, abi, platforms[0])
    expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
    assert result[-1] == expected


def test_generic_sys_tags(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Generic")
    monkeypatch.setattr(tags, "_interpreter_name", lambda: "generic")

    result = list(tags.sys_tags())
    expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
    assert result[-1] == expected
