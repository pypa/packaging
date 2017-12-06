# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import collections
import itertools
import os
import platform
import sys

import pretend
import pytest

from packaging.markers import (
    Node, Variable, Op, Value,
    InvalidMarker, UndefinedComparison, UndefinedEnvironmentName,
    Marker, MarkerExtraParser, MarkerExtraCleaner,
    default_environment, format_full_version,
)


VARIABLES = [
    "extra", "implementation_name", "implementation_version", "os_name",
    "platform_machine", "platform_release", "platform_system",
    "platform_version", "python_full_version", "python_version",
    "platform_python_implementation", "sys_platform",
]

PEP_345_VARIABLES = [
    "os.name", "sys.platform", "platform.version", "platform.machine",
    "platform.python_implementation",
]

SETUPTOOLS_VARIABLES = [
    "python_implementation",
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

    def test_base_class(self):
        with pytest.raises(NotImplementedError):
            Node("cover all the code").serialize()


class TestOperatorEvaluation:

    def test_prefers_pep440(self):
        assert Marker('"2.7.9" < "foo"').evaluate(dict(foo='2.7.10'))

    def test_falls_back_to_python(self):
        assert Marker('"b" > "a"').evaluate(dict(a='a'))

    def test_fails_when_undefined(self):
        with pytest.raises(UndefinedComparison):
            Marker("'2.7.0' ~= os_name").evaluate()


FakeVersionInfo = collections.namedtuple(
    "FakeVersionInfo",
    ["major", "minor", "micro", "releaselevel", "serial"],
)


class TestDefaultEnvironment:

    @pytest.mark.skipif(hasattr(sys, 'implementation'),
                        reason='sys.implementation does exist')
    def test_matches_expected_no_sys_implementation(self):
        environment = default_environment()

        assert environment == {
            "implementation_name": "",
            "implementation_version": "0",
            "os_name": os.name,
            "platform_machine": platform.machine(),
            "platform_release": platform.release(),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "python_full_version": platform.python_version(),
            "platform_python_implementation": platform.python_implementation(),
            "python_version": platform.python_version()[:3],
            "sys_platform": sys.platform,
        }

    @pytest.mark.skipif(not hasattr(sys, 'implementation'),
                        reason='sys.implementation does not exist')
    def test_matches_expected_deleted_sys_implementation(self, monkeypatch):
        monkeypatch.delattr(sys, "implementation")

        environment = default_environment()

        assert environment == {
            "implementation_name": "",
            "implementation_version": "0",
            "os_name": os.name,
            "platform_machine": platform.machine(),
            "platform_release": platform.release(),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "python_full_version": platform.python_version(),
            "platform_python_implementation": platform.python_implementation(),
            "python_version": platform.python_version()[:3],
            "sys_platform": sys.platform,
        }

    @pytest.mark.skipif(not hasattr(sys, 'implementation'),
                        reason='sys.implementation does not exist')
    def test_matches_expected(self):
        environment = default_environment()

        iver = "{0.major}.{0.minor}.{0.micro}".format(
            sys.implementation.version
        )
        if sys.implementation.version.releaselevel != "final":
            iver = "{0}{1[0]}{2}".format(
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
            "platform_python_implementation": platform.python_implementation(),
            "python_version": platform.python_version()[:3],
            "sys_platform": sys.platform,
        }

    @pytest.mark.skipif(hasattr(sys, 'implementation'),
                        reason='sys.implementation does exist')
    def test_monkeypatch_sys_implementation(self, monkeypatch):
        monkeypatch.setattr(
            sys, "implementation",
            pretend.stub(version=FakeVersionInfo(3, 4, 2, "final", 0),
                         name="linux"),
            raising=False)

        environment = default_environment()
        assert environment == {
            "implementation_name": "linux",
            "implementation_version": "3.4.2",
            "os_name": os.name,
            "platform_machine": platform.machine(),
            "platform_release": platform.release(),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "python_full_version": platform.python_version(),
            "platform_python_implementation": platform.python_implementation(),
            "python_version": platform.python_version()[:3],
            "sys_platform": sys.platform,
        }

    def tests_when_releaselevel_final(self):
        v = FakeVersionInfo(3, 4, 2, "final", 0)
        assert format_full_version(v) == '3.4.2'

    def tests_when_releaselevel_not_final(self):
        v = FakeVersionInfo(3, 4, 2, "beta", 4)
        assert format_full_version(v) == '3.4.2b4'


class TestMarker:

    @pytest.mark.parametrize(
        "marker_string",
        [
            "{0} {1} {2!r}".format(*i)
            for i in itertools.product(VARIABLES, OPERATORS, VALUES)
        ] + [
            "{2!r} {1} {0}".format(*i)
            for i in itertools.product(VARIABLES, OPERATORS, VALUES)
        ],
    )
    def test_parses_valid(self, marker_string):
        marker = Marker(marker_string)
        assert marker._marker_string == marker_string

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

    def test_extra_with_no_extra_in_environment(self):
        # We can't evaluate an extra if no extra is passed into the environment
        m = Marker("extra == 'security'")
        with pytest.raises(UndefinedEnvironmentName):
            m.evaluate()

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
            (
                "extra == 'security'",
                {"extra": "quux"},
                False,
            ),
            (
                "extra == 'security'",
                {"extra": "security"},
                True,
            ),
            (
                "extra == 'SECURITY'",
                {"extra": "security"},
                True,
            ),
        ],
    )
    def test_evaluates(self, marker_string, environment, expected):
        args = [] if environment is None else [environment]
        marker = Marker(marker_string)
        assert marker.evaluate(*args) == expected

    @pytest.mark.parametrize(
        ("marker_string", "expected"),
        [
            ("os_name == '{0}'".format(os.name), True),
            ("os_name == 'foo'", True),
            ("os_name == 'foo'", True),
            ("'2.7' in python_version", True),
            ("'2.7' not in python_version", True),
            (
                "os_name == 'foo' and python_version ~= '2.7.0'",
                True,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                True,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                True,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                True,
            ),
            (
                "extra == 'security'",
                True,
            ),
            (
                "extra == 'security'",
                True,
            ),
            (
                "extra == 'SECURITY'",
                True,
            ),
        ],
    )
    def test_parse_marker_not_extra(self, marker_string, expected):
        result = Marker(marker_string).get_marker_not_extra(marker_string)
        assert bool(result) == expected

    @pytest.mark.parametrize(
        "marker_string",
        [
            "{0} {1} {2!r}".format(*i)
            for i in itertools.product(PEP_345_VARIABLES, OPERATORS, VALUES)
        ] + [
            "{2!r} {1} {0}".format(*i)
            for i in itertools.product(PEP_345_VARIABLES, OPERATORS, VALUES)
        ],
    )
    def test_parses_pep345_valid(self, marker_string):
        Marker(marker_string)

    @pytest.mark.parametrize(
        ("marker_string", "environment", "expected"),
        [
            ("os.name == '{0}'".format(os.name), None, True),
            ("sys.platform == 'win32'", {"sys_platform": "linux2"}, False),
            (
                "platform.version in 'Ubuntu'",
                {"platform_version": "#39"},
                False,
            ),
            (
                "platform.machine=='x86_64'",
                {"platform_machine": "x86_64"},
                True,
            ),
            (
                "platform.python_implementation=='Jython'",
                {"platform_python_implementation": "CPython"},
                False,
            ),
            (
                "python_version == '2.5' and platform.python_implementation"
                "!= 'Jython'",
                {"python_version": "2.7"},
                False,
            ),
        ],
    )
    def test_evaluate_pep345_markers(self, marker_string, environment,
                                     expected):
        args = [] if environment is None else [environment]
        assert Marker(marker_string).evaluate(*args) == expected

    @pytest.mark.parametrize(
        "marker_string",
        [
            "{0} {1} {2!r}".format(*i)
            for i in itertools.product(
                SETUPTOOLS_VARIABLES, OPERATORS, VALUES
            )
        ] + [
            "{2!r} {1} {0}".format(*i)
            for i in itertools.product(
                SETUPTOOLS_VARIABLES, OPERATORS, VALUES
            )
        ],
    )
    def test_parses_setuptools_legacy_valid(self, marker_string):
        Marker(marker_string)

    def test_evaluate_setuptools_legacy_markers(self):
        marker_string = "python_implementation=='Jython'"
        args = [{"platform_python_implementation": "CPython"}]
        assert Marker(marker_string).evaluate(*args) is False


class TestMarkerExtraParser:
    @pytest.mark.parametrize(
        ("marker_string", "expected"),
        [
            ("os_name == '{0}'".format(os.name), False),
            ("os_name == 'foo'", False),
            ("os_name == 'foo'", False),
            ("'2.7' in python_version", False),
            ("'2.7' not in python_version", False),
            (
                "os_name == 'foo' and python_version ~= '2.7.0'",
                False,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                False,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                False,
            ),
            (
                "python_version ~= '2.7.0' and (os_name == 'foo' or "
                "os_name == 'bar')",
                False,
            ),
            (
                "extra == 'security'",
                True,
            ),
            (
                "extra == 'security'",
                True,
            ),
            (
                "extra == 'SECURITY'",
                True,
            ),
        ],
    )
    def test_parse_extra_markers(self, marker_string, expected):
        result = MarkerExtraParser.get_extra_markers(marker_string)
        assert bool(result) == expected


class TestExtraMarkerCleaner(object):
    @pytest.mark.parametrize(
        ("markers", "value"),
        [
            (
                [((Variable('extra')), Op('=='), Value('Security'),)],
                'security'
            ),

        ],
    )
    def test_clean_marker_extras(self, markers, value):
        cleaner = MarkerExtraCleaner()
        result = cleaner.clean_marker_extras(markers)
        assert result[0][2].value == value

    @pytest.mark.parametrize(
        ("markers", "value"),
        [
            (
                ((Variable('extra')), Op('=='), Value('Security'),),
                'security'
            ),

        ],
    )
    def test_clean_marker_extra(self, markers, value):
        cleaner = MarkerExtraCleaner()
        result = cleaner._clean_marker_extra(markers)
        assert result[2].value == value

    @pytest.mark.parametrize(
        ("markers", "locations"),
        [
            (
                ((Variable('extra')), Op('=='), Value('Security'),),
                [0]
            ),
            (
                ((Variable('extra')), Op('is'), Value('Security'),),
                [0]
            ),
            (
                ((Variable('extra')), Op('<'), Value('Security'),),
                []
            ),
            (
                (
                    (Variable('extra')),
                    Op('=='),
                    Value('Security'),
                    (Variable('extra')),
                    Op('=='),
                    Value('Security')
                ),
                [0, 3]
            ),
            (
                (
                    (Variable('extra')),
                    Op('=='),
                    (Variable('extra')),
                    (Variable('extra')),
                    Op('=='),
                    Value('Security'),
                ),
                [3]
            ),
            (
                ((Variable('security')), Op('<'), Value('extra'),),
                []
            ),
            (
                ((Variable('extra')), Value('Security'),),
                []
            ),
            (
                ((Variable('security')), Value('extra'), Op('<'), ),
                []
            ),
            (
                ((Variable('security')), Op('<'), Op('<'),),
                []
            ),
            (
                tuple(),
                []
            ),
            (
                (
                    (Variable('extra')),
                    Op('=='),
                    Value('Security'),
                    Value('security')
                ),
                [0]
            ),
        ],
    )
    def test_get_extra_index_location(self, markers, locations):
        cleaner = MarkerExtraCleaner()
        result = cleaner._get_extra_index_location(markers)
        assert result == locations

    @pytest.mark.parametrize(
        ("obj", "object_types", "attribute_names",
         "attribute_values", "expect"),
        [
            (
                Variable('extra'),
                Variable,
                'value',
                'extra',
                True
            ),
            (
                Variable('extra'),
                (Variable, Marker),
                'value',
                'extra',
                True
            ),
            (
                Variable('extra'),
                Variable,
                ('value', 'extra'),
                'extra',
                True
            ),
            (
                Variable('extra'),
                Variable,
                'value',
                ('extra', 'bad value'),
                True
            ),

        ],
    )
    def test_check_attribute(
            self,
            obj,
            object_types,
            attribute_names,
            attribute_values,
            expect
    ):
        cleaner = MarkerExtraCleaner()
        result = cleaner.check_attribute(
            obj, object_types, attribute_names, attribute_values
        )
        assert result == expect
