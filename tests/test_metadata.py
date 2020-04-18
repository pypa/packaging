# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import pytest

from packaging.metadata import (
    Metadata,
    MissingRequiredMetadata,
    RarelyUsedMetadata,
    DeprecatedMetadata,
    MetadataField,
)
from packaging.requirements import Requirement
from packaging.version import parse, Version


MINIMAL_METADATA = {
    "metadata_version": "2.1",
    "name": "BeagleVote",
    "version": "1.0a2",
    "summary": "A module for collecting votes from beagles.",
    "author_email": '"C. Schultz" <cschultz@example.com>',
    "license": "MIT",
}

DEPRECATED_METADATA = {"requires": ["six"], "provides": ["six"], "obsoletes": ["six"]}
RARELY_USED_METDATA = {"provides_dist": ["six"], "obsoletes_dist": ["six"]}



class TestMinimalMetadata:
    def test_minimal(self):
        m = Metadata(**MINIMAL_METADATA)
        assert m.metadata_version == "2.1"
        assert m.name == "BeagleVote"
        assert m.version == parse("1.0a2")
        assert isinstance(m.version, Version)
        assert m.summary == "A module for collecting votes from beagles."
        assert m.author_email == '"C. Schultz" <cschultz@example.com>'
        assert m.license == "MIT"

    @pytest.mark.parametrize("keyword", MINIMAL_METADATA.keys())
    def test_missing_required_metadata(self, keyword):
        invalid_metadata = MINIMAL_METADATA.copy()
        invalid_metadata.pop(keyword)
        with pytest.raises(MissingRequiredMetadata) as e:
            m = Metadata(**invalid_metadata)
        assert "Missing required metadata {}".format(keyword) in str(e.value)


class TestProblematicMetadata:
    @pytest.mark.parametrize(["keyword", "value"], DEPRECATED_METADATA.items())
    def test_deprecated_metadata_warning(self, keyword, value):
        meta_dict = MINIMAL_METADATA.copy()
        meta_dict[keyword] = value
        with pytest.warns(DeprecatedMetadata, match=keyword):
            m = Metadata(**meta_dict)

    @pytest.mark.parametrize(["keyword", "value"], RARELY_USED_METDATA.items())
    def test_rarely_used_metadata_warning(self, keyword, value):
        meta_dict = MINIMAL_METADATA.copy()
        meta_dict[keyword] = value
        with pytest.warns(RarelyUsedMetadata, match=keyword):
            m = Metadata(**meta_dict)

    def test_keyword_commas(self):
        meta_dict = MINIMAL_METADATA.copy()
        meta_dict["keywords"] = "dog,puppy,voting,election"
        m = Metadata(**meta_dict)
        m.keywords == ["dog", "puppy", "voting", "election"]

    def test_keyword_spaces(self):
        meta_dict = MINIMAL_METADATA.copy()
        meta_dict["keywords"] = "dog puppy voting election"
        m = Metadata(**meta_dict)
        m.keywords == ["dog", "puppy", "voting", "election"]


class TestRequirementMetadata:
    def test_requires_dist(self):
        meta_dict = MINIMAL_METADATA.copy()
        meta_dict["requires_dist"] = [
            "pkginfo",
            "PasteDeploy",
            "zope.interface (>3.5.0)",
            "pywin32 >1.0; sys_platform == 'win32'"
        ]
        m = Metadata(**meta_dict)
        for req in meta_dict["requires_dist"]:
            assert Requirement(req) in m.requires_dist

    def test_provides_dist(self):
        meta_dict = MINIMAL_METADATA.copy()
        meta_dict["provides_dist"] = [
            "OtherProject",
            #"AnotherProject (3.4)",
            'virtual_package; python_version >= "3.4"',
        ]
        m = Metadata(**meta_dict)
        for req in meta_dict["provides_dist"]:
            assert Requirement(req) in m.provides_dist

    def test_obsoletes_dist(self):
        meta_dict = MINIMAL_METADATA.copy()
        meta_dict["obsoletes_dist"] = [
            "Gorgon",
            "OtherProject (<3.0)",
            'Foo; os_name == "posix"',
        ]
        m = Metadata(**meta_dict)
        for req in meta_dict["obsoletes_dist"]:
            assert Requirement(req) in m.obsoletes_dist


class TestInformationalMetadata:
    def test_project_url(self):
        meta_dict = MINIMAL_METADATA.copy()
        meta_dict["project_url"] = "Bug Tracker, http://bitbucket.org/tarek/distribute/issues/"
        m = Metadata(**meta_dict)
        assert m.project_url == {
            "Bug Tracker": "http://bitbucket.org/tarek/distribute/issues/"
        }


class TestMetadataField:
    def test_name_conversion(self):
        assert MetadataField("Home-page").python_name == "home_page"
