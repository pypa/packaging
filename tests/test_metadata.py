import pathlib

import pytest

from packaging import metadata, requirements, specifiers, utils, version


class TestRawMetadata:
    @pytest.mark.parametrize("raw_field", metadata._STRING_FIELDS)
    def test_non_repeating_fields_only_once(self, raw_field: set[str]):
        data = "VaLuE"
        header_field = metadata._RAW_TO_EMAIL_MAPPING[raw_field]
        single_header = f"{header_field}: {data}"
        raw, unparsed = metadata.parse_email(single_header)
        assert not unparsed
        assert len(raw) == 1
        assert raw_field in raw
        assert raw[raw_field] == data

    @pytest.mark.parametrize("raw_field", metadata._STRING_FIELDS)
    def test_non_repeating_fields_repeated(self, raw_field: set[str]):
        header_field = metadata._RAW_TO_EMAIL_MAPPING[raw_field]
        data = "VaLuE"
        single_header = f"{header_field}: {data}"
        repeated_header = "\n".join([single_header] * 2)
        raw, unparsed = metadata.parse_email(repeated_header)
        assert not raw
        assert len(unparsed) == 1
        assert header_field in unparsed
        assert unparsed[header_field] == [data] * 2

    @pytest.mark.parametrize("raw_field", metadata._LIST_FIELDS)
    def test_repeating_fields_only_once(self, raw_field: set[str]):
        data = "VaLuE"
        header_field = metadata._RAW_TO_EMAIL_MAPPING[raw_field]
        single_header = f"{header_field}: {data}"
        raw, unparsed = metadata.parse_email(single_header)
        assert not unparsed
        assert len(raw) == 1
        assert raw_field in raw
        assert raw[raw_field] == [data]

    @pytest.mark.parametrize("raw_field", metadata._LIST_FIELDS)
    def test_repeating_fields_repeated(self, raw_field: set[str]):
        header_field = metadata._RAW_TO_EMAIL_MAPPING[raw_field]
        data = "VaLuE"
        single_header = f"{header_field}: {data}"
        repeated_header = "\n".join([single_header] * 2)
        raw, unparsed = metadata.parse_email(repeated_header)
        assert not unparsed
        assert len(raw) == 1
        assert raw_field in raw
        assert raw[raw_field] == [data] * 2

    @pytest.mark.parametrize(
        ["given", "expected"],
        [
            ("A", ["A"]),
            ("A ", ["A"]),
            (" A", ["A"]),
            ("A, B", ["A", "B"]),
            ("A,B", ["A", "B"]),
            (" A, B", ["A", "B"]),
            ("A,B ", ["A", "B"]),
            ("A B", ["A B"]),
        ],
    )
    def test_keywords(self, given, expected):
        header = f"Keywords: {given}"
        raw, unparsed = metadata.parse_email(header)
        assert not unparsed
        assert len(raw) == 1
        assert "keywords" in raw
        assert raw["keywords"] == expected

    @pytest.mark.parametrize(
        ["given", "expected"],
        [
            ("", {"": ""}),
            ("A", {"A": ""}),
            ("A,B", {"A": "B"}),
            ("A, B", {"A": "B"}),
            (" A,B", {"A": "B"}),
            ("A,B ", {"A": "B"}),
            ("A,B,C", {"A": "B,C"}),
        ],
    )
    def test_project_urls_parsing(self, given, expected):
        header = f"project-url: {given}"
        raw, unparsed = metadata.parse_email(header)
        assert not unparsed
        assert len(raw) == 1
        assert "project_urls" in raw
        assert raw["project_urls"] == expected

    def test_duplicate_project_urls(self):
        header = "project-url: A, B\nproject-url: A, C"
        raw, unparsed = metadata.parse_email(header)
        assert not raw
        assert len(unparsed) == 1
        assert "project-url" in unparsed
        assert unparsed["project-url"] == ["A, B", "A, C"]

    def test_str_input(self):
        name = "Tarek Ziadé"
        header = f"author: {name}"
        raw, unparsed = metadata.parse_email(header)
        assert not unparsed
        assert len(raw) == 1
        assert "author" in raw
        assert raw["author"] == name

    def test_bytes_input(self):
        name = "Tarek Ziadé"
        header = f"author: {name}".encode()
        raw, unparsed = metadata.parse_email(header)
        assert not unparsed
        assert len(raw) == 1
        assert "author" in raw
        assert raw["author"] == name

    def test_header_mojibake(self):
        value = "\xc0msterdam"
        header_name = "value"
        header_bytes = f"{header_name}: {value}".encode("latin1")
        raw, unparsed = metadata.parse_email(header_bytes)
        # Sanity check
        with pytest.raises(UnicodeDecodeError):
            header_bytes.decode("utf-8")
        assert not raw
        assert len(unparsed) == 1
        assert header_name in unparsed
        assert unparsed[header_name] == [value]

    @pytest.mark.parametrize(
        ["given"], [("hello",), ("description: hello",), (b"hello",)]
    )
    def test_description(self, given):
        raw, unparsed = metadata.parse_email(given)
        assert not unparsed
        assert len(raw) == 1
        assert "description" in raw
        assert raw["description"] == "hello"

    def test_description_non_utf8(self):
        header = "\xc0msterdam"
        header_bytes = header.encode("latin1")
        raw, unparsed = metadata.parse_email(header_bytes)
        assert not raw
        assert len(unparsed) == 1
        assert "description" in unparsed
        assert unparsed["description"] == [header_bytes]

    @pytest.mark.parametrize(
        ["given", "expected"],
        [
            ("description: 1\ndescription: 2", ["1", "2"]),
            ("description: 1\n\n2", ["1", "2"]),
            ("description: 1\ndescription: 2\n\n3", ["1", "2", "3"]),
        ],
    )
    def test_description_multiple(self, given, expected):
        raw, unparsed = metadata.parse_email(given)
        assert not raw
        assert len(unparsed) == 1
        assert "description" in unparsed
        assert unparsed["description"] == expected

    def test_lowercase_keys(self):
        header = "AUTHOR: Tarek Ziadé\nWhatever: Else"
        raw, unparsed = metadata.parse_email(header)
        assert len(raw) == 1
        assert "author" in raw
        assert len(unparsed) == 1
        assert "whatever" in unparsed

    def test_complete(self):
        """Test all fields (except `Obsoletes-Dist`).

        `Obsoletes-Dist` was sacrificed to provide a value for `Dynamic`.
        """
        path = pathlib.Path(__file__).parent / "metadata" / "everything.metadata"
        with path.open("r", encoding="utf-8") as file:
            metadata_contents = file.read()
        raw, unparsed = metadata.parse_email(metadata_contents)
        assert len(unparsed) == 1
        assert unparsed["thisisnotreal"] == ["Hello!"]
        assert len(raw) == 24
        assert raw["metadata_version"] == "2.3"
        assert raw["name"] == "BeagleVote"
        assert raw["version"] == "1.0a2"
        assert raw["platforms"] == ["ObscureUnix", "RareDOS"]
        assert raw["supported_platforms"] == ["RedHat 7.2", "i386-win32-2791"]
        assert raw["summary"] == "A module for collecting votes from beagles."
        assert (
            raw["description_content_type"]
            == "text/markdown; charset=UTF-8; variant=GFM"
        )
        assert raw["keywords"] == ["dog", "puppy", "voting", "election"]
        assert raw["home_page"] == "http://www.example.com/~cschultz/bvote/"
        assert raw["download_url"] == "…/BeagleVote-0.45.tgz"
        assert raw["author"] == (
            "C. Schultz, Universal Features Syndicate,\n"
            "        Los Angeles, CA <cschultz@peanuts.example.com>"
        )
        assert raw["author_email"] == '"C. Schultz" <cschultz@example.com>'
        assert raw["maintainer"] == (
            "C. Schultz, Universal Features Syndicate,\n"
            "        Los Angeles, CA <cschultz@peanuts.example.com>"
        )
        assert raw["maintainer_email"] == '"C. Schultz" <cschultz@example.com>'
        assert raw["license"] == (
            "This software may only be obtained by sending the\n"
            "        author a postcard, and then the user promises not\n"
            "        to redistribute it."
        )
        assert raw["classifiers"] == [
            "Development Status :: 4 - Beta",
            "Environment :: Console (Text Based)",
        ]
        assert raw["provides_extra"] == ["pdf"]
        assert raw["requires_dist"] == [
            "reportlab; extra == 'pdf'",
            "pkginfo",
            "PasteDeploy",
            "zope.interface (>3.5.0)",
            "pywin32 >1.0; sys_platform == 'win32'",
        ]
        assert raw["requires_python"] == ">=3"
        assert raw["requires_external"] == [
            "C",
            "libpng (>=1.5)",
            'make; sys_platform != "win32"',
        ]
        assert raw["project_urls"] == {
            "Bug Tracker": "http://bitbucket.org/tarek/distribute/issues/",
            "Documentation": "https://example.com/BeagleVote",
        }
        assert raw["provides_dist"] == [
            "OtherProject",
            "AnotherProject (3.4)",
            'virtual_package; python_version >= "3.4"',
        ]
        assert raw["dynamic"] == ["Obsoletes-Dist"]
        assert raw["description"] == "This description intentionally left blank.\n"


class TestMetadata:
    def test_from_email(self):
        metadata_version = "2.3"
        meta = metadata.Metadata.from_email(f"Metadata-Version: {metadata_version}")

        assert meta.metadata_version == metadata_version

    @pytest.mark.parametrize(
        "attribute",
        [
            "description",
            "home_page",
            "download_url",
            "author",
            "author_email",
            "maintainer",
            "maintainer_email",
            "license",
        ],
    )
    def test_single_value_unvalidated_attribute(self, attribute):
        value = "Not important"
        meta = metadata.Metadata.from_raw({attribute: value})

        assert getattr(meta, attribute) == value

    @pytest.mark.parametrize(
        "attribute",
        [
            "supported_platforms",
            "platforms",
            "classifiers",
            "provides_dist",
            "obsoletes_dist",
        ],
    )
    def test_multi_value_unvalidated_attribute(self, attribute):
        values = ["Not important", "Still not important"]
        meta = metadata.Metadata.from_raw({attribute: values})

        assert getattr(meta, attribute) == values

    @pytest.mark.parametrize(
        "version", ["1.0", "1.1", "1.2", "2.0", "2.1", "2.2", "2.3"]
    )
    def test_valid_metadata_version(self, version):
        meta = metadata.Metadata.from_raw({"metadata_version": version})

        assert meta.metadata_version == version

    def test_invalid_metadata_version(self):
        meta = metadata.Metadata.from_raw({"metadata_version": "1.3"})

        with pytest.raises(metadata.InvalidMetadata):
            meta.metadata_version

    def test_valid_version(self):
        version_str = "1.2.3"
        meta = metadata.Metadata.from_raw({"version": version_str})
        assert meta.version == version.parse(version_str)

    def test_missing_version(self):
        meta = metadata.Metadata.from_raw({})
        with pytest.raises(metadata.InvalidMetadata) as exc_info:
            meta.version
        assert exc_info.value.field == "version"

    def test_invalid_version(self):
        meta = metadata.Metadata.from_raw({"version": "a.b.c"})

        with pytest.raises(version.InvalidVersion):
            meta.version

    def test_valid_summary(self):
        summary = "Hello"
        meta = metadata.Metadata.from_raw({"summary": summary})

        assert meta.summary == summary

    def test_invalid_summary(self):
        meta = metadata.Metadata.from_raw({"summary": "Hello\n    Again"})

        with pytest.raises(metadata.InvalidMetadata) as exc_info:
            meta.summary
        assert exc_info.value.field == "summary"

    def test_valid_name(self):
        name = "Hello_World"
        meta = metadata.Metadata.from_raw({"name": name})
        assert meta.name == utils.canonicalize_name(name)

    def test_invalid_name(self):
        meta = metadata.Metadata.from_raw({"name": "-not-legal"})

        with pytest.raises(utils.InvalidName):
            meta.name

    @pytest.mark.parametrize(
        "content_type",
        [
            "text/plain",
            "text/x-rst",
            "text/markdown",
            "text/plain; charset=UTF-8",
            "text/x-rst; charset=UTF-8",
            "text/markdown; charset=UTF-8; variant=GFM",
            "text/markdown; charset=UTF-8; variant=CommonMark",
            "text/markdown; variant=GFM",
            "text/markdown; variant=CommonMark",
        ],
    )
    def test_valid_description_content_type(self, content_type):
        meta = metadata.Metadata.from_raw({"description_content_type": content_type})

        assert meta.description_content_type == content_type

    @pytest.mark.parametrize(
        "content_type",
        [
            "application/json",
            "TEXT/PLAIN",
            "text/plain; charset=ascii",
            "text/plain; charset=utf-8",
            "text/markdown; variant=gfm",
            "text/markdown; variant=commonmark",
        ],
    )
    def test_invalid_description_content_type(self, content_type):
        meta = metadata.Metadata.from_raw({"description_content_type": content_type})

        with pytest.raises(metadata.InvalidMetadata):
            meta.description_content_type

    def test_keywords(self):
        keywords = ["hello", "world"]
        meta = metadata.Metadata.from_raw({"keywords": keywords})

        assert meta.keywords == keywords

    def test_project_urls(self):
        urls = {
            "Documentation": "https://example.com/BeagleVote",
            "Bug Tracker": "http://bitbucket.org/tarek/distribute/issues/",
        }
        meta = metadata.Metadata.from_raw({"project_urls": urls})

        assert meta.project_urls == urls

    @pytest.mark.parametrize("specifier", [">=3", ">2.6,!=3.0.*,!=3.1.*", "~=2.6"])
    def test_valid_requires_python(self, specifier):
        expected = specifiers.SpecifierSet(specifier)
        meta = metadata.Metadata.from_raw({"requires_python": specifier})

        assert meta.requires_python == expected

    def test_invalid_requires_python(self):
        meta = metadata.Metadata.from_raw({"requires_python": "NotReal"})
        with pytest.raises(specifiers.InvalidSpecifier):
            meta.requires_python

    def test_requires_external(self):
        externals = [
            "C",
            "libpng (>=1.5)",
            'make; sys_platform != "win32"',
            "libjpeg (>6b)",
        ]
        meta = metadata.Metadata.from_raw({"requires_external": externals})

        assert meta.requires_external == externals

    def test_valid_provides_extra(self):
        extras = ["dev", "test"]
        meta = metadata.Metadata.from_raw({"provides_extra": extras})

        assert meta.provides_extra == extras

    def test_invalid_provides_extra(self):
        extras = ["pdf", "-Not-Valid", "ok"]
        meta = metadata.Metadata.from_raw({"provides_extra": extras})

        with pytest.raises(utils.InvalidName):
            meta.provides_extra

    def test_valid_requires_dist(self):
        requires = [
            "pkginfo",
            "PasteDeploy",
            "zope.interface (>3.5.0)",
            "pywin32 >1.0; sys_platform == 'win32'",
        ]
        expected_requires = list(map(requirements.Requirement, requires))
        meta = metadata.Metadata.from_raw({"requires_dist": requires})

        assert meta.requires_dist == expected_requires

    def test_invalid_requires_dist(self):
        requires = ["pkginfo", "-not-real", "zope.interface (>3.5.0)"]
        meta = metadata.Metadata.from_raw({"requires_dist": requires})

        with pytest.raises(requirements.InvalidRequirement):
            meta.requires_dist

    def test_valid_dynamic(self):
        dynamic = ["Keywords", "Home-Page", "Author"]
        meta = metadata.Metadata.from_raw({"dynamic": dynamic})

        assert meta.dynamic == [d.lower() for d in dynamic]

    def test_invalid_dynamic(self):
        dynamic = ["Keywords", "NotReal", "Author"]
        meta = metadata.Metadata.from_raw({"dynamic": dynamic})

        with pytest.raises(metadata.InvalidMetadata):
            meta.dynamic

    @pytest.mark.parametrize("field_name", ["name", "version", "metadata-version"])
    def test_disallowed_dynamic(self, field_name):
        meta = metadata.Metadata.from_raw({"dynamic": field_name})

        with pytest.raises(metadata.InvalidMetadata):
            meta.dynamic
