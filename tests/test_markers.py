# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import collections
import itertools
import os
import platform
import sys

import pytest

from packaging.markers import (
    Node, InvalidMarker, UndefinedComparison, Marker, _eval_op,
    default_environment,
)


VARIABLES = [
    "extra", "implementation_version", "implementation_version", "os_name",
    "platform_machine", "platform_release", "platform_system",
    "platform_version", "python_full_version", "python_implementation",
    "python_version", "sys_platform",
]

OPERATORS = [
    "===", "==", ">=", "<=", "!=", "~=", ">", "<", "in", "not in",
]

VALUES = [
    "1.0", "5.6a0", "dog", "freebsd", "literally any string can go here",
    "things @#4 dsfd (((",
]


class TestNode:

    @pytest.mark.parametrize("value", ["one", "two", None, 3, 5, []])
    def test_accepts_value(self, value):
        assert Node(value).value == value

    @pytest.mark.parametrize("value", ["one", "two", None, 3, 5, []])
    def test_str(self, value):
        assert str(Node(value)) == str(value)

    @pytest.mark.parametrize("value", ["one", "two", None, 3, 5, []])
    def test_repr(self, value):
        assert repr(Node(value)) == "<Node({0!r})>".format(str(value))


class TestOperatorEvaluation:

    def test_prefers_pep440(self):
        assert _eval_op("2.7.10", ">", "2.7.9")

    def test_falls_back_to_python(self):
        assert _eval_op("b", ">", "a")

    def test_fails_when_undefined(self):
        with pytest.raises(UndefinedComparison):
            _eval_op("2.7.0", "~=", "invalid")


FakeVersionInfo = collections.namedtuple(
    "FakeVersionInfo",
    ["major", "minor", "micro", "releaselevel", "serial"],
)


class TestDefaultEnvironment:

    def test_matches_expected(self):
        environment = default_environment()

        iver = "{0.major}.{0.minor}.{0.micro}".format(
            sys.implementation.version
        )
        if sys.implementation.version.releaselevel != "final":
            iver = "{0}{1}[0]{2}".format(
                iver,
                sys.implementation.version.releaselevel,
                sys.implementation.version.serial,
            )

        assert environment == {
            "implementation_name": sys.implementation.name,
            "implementation_version": iver,
            "os_name": os.name,
            "platform_machine": platform.machine(),
            "platform_release": platform.release(),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "python_full_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version()[:3],
            "sys_platform": sys.platform,
        }

    def tests_when_releaselevel_final(self, monkeypatch):
        monkeypatch.setattr(
            sys.implementation,
            "version",
            FakeVersionInfo(*sys.implementation.version[:3] + ("final", 0)),
        )

        environment = default_environment()

        assert environment == {
            "implementation_name": sys.implementation.name,
            "implementation_version": "{0.major}.{0.minor}.{0.micro}".format(
                sys.implementation.version
            ),
            "os_name": os.name,
            "platform_machine": platform.machine(),
            "platform_release": platform.release(),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "python_full_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version()[:3],
            "sys_platform": sys.platform,
        }

    def tests_when_releaselevel_not_final(self, monkeypatch):
        monkeypatch.setattr(
            sys.implementation,
            "version",
            FakeVersionInfo(*sys.implementation.version[:3] + ("beta", 4)),
        )

        environment = default_environment()
        v = "{0.major}.{0.minor}.{0.micro}{0.releaselevel[0]}{0.serial}"

        assert environment == {
            "implementation_name": sys.implementation.name,
            "implementation_version": v.format(sys.implementation.version),
            "os_name": os.name,
            "platform_machine": platform.machine(),
            "platform_release": platform.release(),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "python_full_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version()[:3],
            "sys_platform": sys.platform,
        }


class TestMarker:

    @pytest.mark.parametrize(
        "marker_string",
        [
            "{0} {1} {2!r}".format(*i)
            for i in itertools.product(VARIABLES, OPERATORS, VALUES)
        ]
        +
        [
            "{2!r} {1} {0}".format(*i)
            for i in itertools.product(VARIABLES, OPERATORS, VALUES)
        ],
    )
    def test_parses_valid(self, marker_string):
        Marker(marker_string)

    @pytest.mark.parametrize(
        "marker_string",
        [
            "this_isnt_a_real_variable >= '1.0'",
            "python_version",
            "(python_version)",
            "python_version >= 1.0 and (python_version)",
        ],
    )
    def test_parses_invalid(self, marker_string):
        with pytest.raises(InvalidMarker):
            Marker(marker_string)

    @pytest.mark.parametrize(
        ("marker_string", "expected"),
        [
            # Test the different quoting rules
            ("python_version == '2.7'", 'python_version == "2.7"'),
            ('python_version == "2.7"', 'python_version == "2.7"'),

            # Test and/or expressions
            (
                'python_version == "2.7" and os_name == "linux"',
                'python_version == "2.7" and os_name == "linux"',
            ),
            (
                'python_version == "2.7" or os_name == "linux"',
                'python_version == "2.7" or os_name == "linux"',
            ),
            (
                'python_version == "2.7" and os_name == "linux" or '
                'sys_platform == "win32"',
                'python_version == "2.7" and os_name == "linux" or '
                'sys_platform == "win32"',
            ),

            # Test nested expressions and grouping with ()
            ('(python_version == "2.7")', 'python_version == "2.7"'),
            (
                '(python_version == "2.7" and sys_platform == "win32")',
                'python_version == "2.7" and sys_platform == "win32"',
            ),
            (
                'python_version == "2.7" and (sys_platform == "win32" or '
                'sys_platform == "linux")',
                'python_version == "2.7" and (sys_platform == "win32" or '
                'sys_platform == "linux")',
            ),
        ],
    )
    def test_str_and_repr(self, marker_string, expected):
        m = Marker(marker_string)
        assert str(m) == expected
        assert repr(m) == "<Marker({0!r})>".format(str(m))

    @pytest.mark.parametrize(
        ("marker_string", "environment", "expected"),
        [
            ("os_name == '{0}'".format(os.name), None, True),
            ("os_name == 'foo'", {"os_name": "foo"}, True),
            ("os_name == 'foo'", {"os_name": "bar"}, False),
            ("'2.7' in python_version", {"python_version": "2.7.5"}, True),
            ("'2.7' not in python_version", {"python_version": "2.7"}, False),
            (
                "os_name == 'foo' and python_version ~= '2.7.0'",
                {"os_name": "foo", "python_version": "2.7.6"},
                True,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                {"os_name": "foo", "python_version": "2.7.4"},
                True,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                {"os_name": "bar", "python_version": "2.7.4"},
                True,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                {"os_name": "other", "python_version": "2.7.4"},
                False,
            ),
        ],
    )
    def test_evaluates(self, marker_string, environment, expected):
        args = [] if environment is None else [environment]
        assert Marker(marker_string).evaluate(*args) == expected
