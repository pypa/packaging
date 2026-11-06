import json
import typing
from typing import TypeGuard

import pytest

from packaging import index

HTML_CONTENT_TYPE = index._ACCEPT_HTML_VALUES[0]


def is_exception(exc: object) -> TypeGuard[type[index.IndexServerException]]:
    return isinstance(exc, type) and issubclass(exc, index.IndexServerException)


class ParseBaseTests:
    def test_invalid_content_type(self, content_type: str) -> None:
        raise NotImplementedError

    def test_html_content_type(self, content_type: str) -> None:
        raise NotImplementedError

    def test_json_content_type(self, content_type: str) -> None:
        raise NotImplementedError

    def test_html_api_version(self, meta_tag: str, api_version: str) -> None:
        raise NotImplementedError

    def test_html_unknown_meta_tag_name(self) -> None:
        raise NotImplementedError

    def test_html_data_whitespace(self) -> None:
        raise NotImplementedError

    def test_html_extra_tags(self) -> None:
        raise NotImplementedError

    def test_html_worthless_a_tag(self, tag_contents: str) -> None:
        raise NotImplementedError


class TestParseList(ParseBaseTests):
    @pytest.mark.parametrize(
        "content_type", [*index._ACCEPT_HTML_VALUES, "text/html; charset=utf-8"]
    )
    def test_html_content_type(self, content_type: str) -> None:
        html_spec_example = """
            <!DOCTYPE html>
            <html>
            <body>
                <a href="/frob/">frob</a>
                <a href="/spamspamspam/">spamspamspam</a>
            </body>
            </html>
        """
        result = index.parse_list(content_type, html_spec_example)
        expect: index.RawProjectList = {
            "meta": {"api-version": "1.0"},
            "projects": [{"name": "frob"}, {"name": "spamspamspam"}],
        }
        assert result == expect

    @pytest.mark.parametrize(
        "content_type", [index.ACCEPT_JSON_V1, index.ACCEPT_JSON_V1 + ";charset=utf-8"]
    )
    def test_json_content_type(self, content_type: str) -> None:
        expect: index.RawProjectList = {
            "meta": {"api-version": "1.0"},
            "projects": [{"name": "frob"}, {"name": "spamspamspam"}],
        }
        result = index.parse_list(content_type, json.dumps(expect))
        assert result == expect

    @pytest.mark.parametrize(
        "content_type", [index.ACCEPT_JSON_V1 + "spam", HTML_CONTENT_TYPE + "spam"]
    )
    def test_invalid_content_type(self, content_type: str) -> None:
        with pytest.raises(index.InvalidContentType):
            index.parse_list(content_type, "")

    @pytest.mark.parametrize(
        ("meta_tag", "api_version"),
        [
            ("", "1.0"),
            ('<meta name="pypi:repository-version" content="1.4"></meta>', "1.4"),
            ('<meta name="pypi:repository-version" content="1.4">', "1.4"),
            ('<meta name="pypi:repository-version" content="1.4" />', "1.4"),
            ('<meta content="1.4" ></meta>', "1.0"),
            (
                '<meta name="pypi:repository-version"></meta>',
                index.InvalidHTMLAttributeValue,
            ),
        ],
    )
    def test_html_api_version(
        self, meta_tag: str, api_version: str | type[index.IndexServerException]
    ) -> None:
        html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                {meta_tag}
            </head>
            <body>
                <a href="/frob/">frob</a>
                <a href="/spamspamspam/">spamspamspam</a>
            </body>
            </html>
        """
        if is_exception(api_version):
            with pytest.raises(api_version):
                index.parse_list(HTML_CONTENT_TYPE, html)
        else:
            expect: index.RawProjectList = typing.cast(
                "index.RawProjectList",
                {
                    "meta": {"api-version": api_version},
                    "projects": [{"name": "frob"}, {"name": "spamspamspam"}],
                },
            )
            result = index.parse_list(HTML_CONTENT_TYPE, html)

            assert result == expect

    def test_html_unknown_meta_tag_name(self) -> None:
        html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="pypi:not-real" content="boo" ignore="me" />
            </head>
            <body>
                <a href="/frob/">frob</a>
                <a href="/spamspamspam/">spamspamspam</a>
            </body>
            </html>
        """

        expect: index.RawProjectList = typing.cast(
            "index.RawProjectList",
            {
                "meta": {"api-version": "1.0"},
                "projects": [{"name": "frob"}, {"name": "spamspamspam"}],
            },
        )
        result = index.parse_list(HTML_CONTENT_TYPE, html)

        assert result == expect

    def test_html_data_whitespace(self) -> None:
        html = """
            <!DOCTYPE html>
            <html>
            <body>
                <a href="/frob/">
                    <!-- This should be ignored. -->
                    frob
                </a>
                <a href="/spamspamspam/">
                    spamspam<!-- bacon -->spam
                </a>
            </body>
            </html>
        """
        expect: index.RawProjectList = {
            "meta": {"api-version": "1.0"},
            "projects": [{"name": "frob"}, {"name": "spamspamspam"}],
        }
        result = index.parse_list("text/html", html)
        assert result == expect

    def test_html_extra_tags(self) -> None:
        html_spec_example = """
            <!DOCTYPE html>
            <html>
            <body>
                <a href="/frob/">frob</a><br />
                <a href="/spamspamspam/">spamspamspam</a>
            </body>
            </html>
        """
        result = index.parse_list(HTML_CONTENT_TYPE, html_spec_example)
        expect: index.RawProjectList = {
            "meta": {"api-version": "1.0"},
            "projects": [{"name": "frob"}, {"name": "spamspamspam"}],
        }
        assert result == expect

    @pytest.mark.parametrize("tag_contents", ['<a href="/frob/"></a>', "<a href></a>"])
    def test_html_worthless_a_tag(self, tag_contents: str) -> None:
        given = f"""
            <!DOCTYPE html>
            <html>
            <body>
                {tag_contents}
            </body>
            </html>
        """
        result = index.parse_list(HTML_CONTENT_TYPE, given)
        expect: index.RawProjectList = {
            "meta": {"api-version": "1.0"},
            "projects": [],
        }
        assert result == expect

    def test_canonical_names_json(self) -> None:
        given: index.RawProjectList = {
            "meta": {"api-version": "1.0"},
            "projects": [{"name": "Frob"}, {"name": "Spam_Spam_spam"}],
        }
        expect: index.RawProjectList = {
            "meta": {"api-version": "1.0"},
            "projects": [{"name": "frob"}, {"name": "spam-spam-spam"}],
        }
        result = index.parse_list(index.ACCEPT_JSON_V1, json.dumps(given))
        assert result == expect

    def test_canonical_names_html(self) -> None:
        html = (
            '<html><body><a href="/Frob/">Frob</a>'
            '<a href="/Spam_Spam_spam/">Spam_Spam_spam</a></body></html>'
        )
        expect: index.RawProjectList = {
            "meta": {"api-version": "1.0"},
            "projects": [{"name": "frob"}, {"name": "spam-spam-spam"}],
        }
        result = index.parse_list("text/html", html)
        assert result == expect


class TestParseDetails(ParseBaseTests):
    @pytest.mark.parametrize(
        "content_type", [index.ACCEPT_JSON_V1 + "spam", HTML_CONTENT_TYPE + "spam"]
    )
    def test_invalid_content_type(self, content_type: str) -> None:
        with pytest.raises(index.InvalidContentType):
            index.parse_details(content_type, "", name="spam")

    @pytest.mark.parametrize(
        "content_type", [*index._ACCEPT_HTML_VALUES, "text/html; charset=utf-8"]
    )
    def test_html_content_type(self, content_type: str) -> None:
        given = """
            <html>
            <body>
            <a href="https://files.pythonhosted.org/spam/spam-1.0.tar.gz">spam-1.0.tar.gz</a>
            </body>
            </html>
        """
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                    "hashes": {},
                }
            ],
        }
        result = index.parse_details(content_type, given, name="spam")

        assert result == expect

    @pytest.mark.parametrize(
        "content_type", [index.ACCEPT_JSON_V1, index.ACCEPT_JSON_V1 + ";charset=utf-8"]
    )
    def test_json_content_type(self, content_type: str) -> None:
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                    "hashes": {},
                }
            ],
        }
        result = index.parse_details(content_type, json.dumps(expect), name="spam")
        assert result == expect

    @pytest.mark.parametrize(
        "url",
        [
            "https://pypi.org/simple/spam-spam/",
            "https://pypi.irg/simple/spam-spam",
            "https://pypi.irg/simple/spAm_Spam",
        ],
    )
    def test_html_name_from_url(self, url: str) -> None:
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam-spam",
            "files": [],
        }
        result = index.parse_details(HTML_CONTENT_TYPE, "", request_url=url)

        assert result == expect

    @pytest.mark.parametrize(
        ("meta_tag", "api_version"),
        [
            ("", "1.0"),
            ('<meta name="pypi:repository-version" content="1.4"></meta>', "1.4"),
            ('<meta name="pypi:repository-version" content="1.4">', "1.4"),
            ('<meta name="pypi:repository-version" content="1.4" />', "1.4"),
            ('<meta content="1.4" ></meta>', "1.0"),
            (
                '<meta name="pypi:repository-version"></meta>',
                index.InvalidHTMLAttributeValue,
            ),
        ],
    )
    def test_html_api_version(
        self, meta_tag: str, api_version: str | type[index.IndexServerException]
    ) -> None:
        given = f"""
            <html>
            <head>
                {meta_tag}
            <body>
                <a href="https://files.pythonhosted.org/spam/spam-1.0.tar.gz">spam-1.0.tar.gz</a>
            </body>
            </html>
        """
        if is_exception(api_version):
            with pytest.raises(api_version):
                index.parse_details(HTML_CONTENT_TYPE, given, name="spam")
        else:
            expect: index.RawProjectDetails = typing.cast(
                "index.RawProjectDetails",
                {
                    "meta": {"api-version": api_version},
                    "name": "spam",
                    "files": [
                        {
                            "filename": "spam-1.0.tar.gz",
                            "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                            "hashes": {},
                        }
                    ],
                },
            )
            result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

            assert result == expect

    def test_html_unknown_meta_tag_name(self) -> None:
        given = """
            <html>
            <head>
                <meta name="pypi:not-real" content="boo" />
            <body>
                <a href="https://files.pythonhosted.org/spam/spam-1.0.tar.gz">spam-1.0.tar.gz</a>
            </body>
            </html>
        """

        expect: index.RawProjectDetails = typing.cast(
            "index.RawProjectDetails",
            {
                "meta": {"api-version": "1.0"},
                "name": "spam",
                "files": [
                    {
                        "filename": "spam-1.0.tar.gz",
                        "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                        "hashes": {},
                    }
                ],
            },
        )
        result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

        assert result == expect

    def test_html_data_whitespace(self) -> None:
        given = """
            <html>
            <body>
            <a href="https://files.pythonhosted.org/spam/spam-1.0.tar.gz">
                <!-- Comments are ignored. -->
                spam-1.0<!-- ... -->.tar.gz
            </a>
            </body>
            </html>
        """
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                    "hashes": {},
                }
            ],
        }
        result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

        assert result == expect

    def test_html_extra_tags(self) -> None:
        given = """
            <html>
            <body>
            <a href="https://files.pythonhosted.org/spam/spam-1.0.tar.gz">spam-1.0.tar.gz</a><br />
            </body>
            </html>
        """  # noqa: E501
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                    "hashes": {},
                }
            ],
        }
        result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

        assert result == expect

    @pytest.mark.parametrize("tag_contents", ["a", "a href"])
    def test_html_worthless_a_tag(self, tag_contents: str) -> None:
        given = f"""
            <html>
            <body>
            <{tag_contents}>spam-1.0.tar.gz</a>
            </body>
            </html>
        """
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [],
        }
        result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

        assert result == expect

    @pytest.mark.parametrize(
        ("given_status", "expect_status", "ok"),
        [
            ("active", "active", True),
            ("archived", "archived", True),
            ("quarantined", "quarantined", True),
            ("deprecated", "deprecated", True),
            ("Active", "active", True),
            ("spam", "", False),
        ],
    )
    def test_html_project_status(
        self, given_status: str, expect_status: str, ok: bool
    ) -> None:
        given = f"""
            <html>
            <meta name="pypi:project-status" content="{given_status}" />
            </html>
        """
        if not ok:
            with pytest.raises(index.InvalidHTMLAttributeValue):
                index.parse_details(HTML_CONTENT_TYPE, given, name="spam")
        else:
            expect: index.RawProjectDetails = typing.cast(
                "index.RawProjectDetails",
                {
                    "meta": {"api-version": "1.0"},
                    "name": "spam",
                    "project-status": {"status": expect_status},
                    "files": [],
                },
            )
            result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

            assert result == expect

    @pytest.mark.parametrize("reason", ["something", ""])
    def test_html_project_reason(self, reason: str) -> None:
        given = f"""
            <html>
            <meta name="pypi:project-status-reason" content="{reason}" />
            </html>
        """
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "project-status": {"reason": reason},
            "files": [],
        }
        result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

        assert result == expect

    def test_html_project_status_complete(self) -> None:
        given = """
            <html>
            <meta name="pypi:project-status" content="active" />
            <meta name="pypi:project-status-reason" content="something" />
            </html>
        """
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "project-status": {"status": "active", "reason": "something"},
            "files": [],
        }
        result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

        assert result == expect

    def test_json_hash_algorithm_normalization(self) -> None:
        given = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": "https://example.com/spam/spam-1.0.tar.gz",
                    "hashes": {"SHA256": "abcd12345"},
                }
            ],
        }
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": "https://example.com/spam/spam-1.0.tar.gz",
                    "hashes": {"sha256": "abcd12345"},
                }
            ],
        }
        result = index.parse_details(
            index.ACCEPT_JSON_V1, json.dumps(given), name="spam"
        )

        assert result == expect

    @pytest.mark.parametrize(
        ("fragment", "hash"),
        [
            # Guaranteed algorithm
            ("sha256=abcd1234", {"sha256": "abcd1234"}),
            # Hash algorithm name not lowercase
            ("SHA256=abcd1234", {"sha256": "abcd1234"}),
            # Available algorithm
            ("sha512_256=abcd1234", {"sha512_256": "abcd1234"}),
            # Multiple algorithms
            (
                "sha256=abcd1234&sha512=1234abcd",
                {"sha256": "abcd1234", "sha512": "1234abcd"},
            ),
            # Extra fragment items are ignored
            ("subdir=spam&sha256=abcd1234", {"sha256": "abcd1234"}),
            ("sha256=abcd1234&subdir=spam", {"sha256": "abcd1234"}),
            # Malformed
            ("sha256==abcd1234", {}),
            ("sha256=", {}),
            ("=abcd1234", {}),
            ("sha256", {}),
            ("spam", {}),
            # Not hash algorithms
            ("egg=spam", {}),
            ("spam=1234", {}),
        ],
    )
    def test_html_hashes(self, fragment: str, hash: dict[str, str]) -> None:
        url = "https://pypi.org/spam/spam-1.0.tar.gz#" + fragment
        given = f"""
            <html>
            <body>
            <a href="{url}">spam-1.0.tar.gz</a>
            </body>
            </html>
        """
        expect: index.RawProjectDetails = typing.cast(
            "index.RawProjectDetails",
            {
                "meta": {"api-version": "1.0"},
                "name": "spam",
                "files": [
                    {
                        "filename": "spam-1.0.tar.gz",
                        "url": url,
                        "hashes": hash,
                    }
                ],
            },
        )
        result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

        assert result == expect

    @pytest.mark.parametrize(
        ("attr_value", "json_value"),
        [
            ("=true", True),
            ("", True),  # Spec doesn't say this is right, but it's unambiguous.
            ('="sha256=12345abcde"', {"sha256": "12345abcde"}),
            ('="SHA256=12345abcde"', {"sha256": "12345abcde"}),
            ('="sha256="', index.InvalidHTMLAttributeValue),
            ('="=12345abcde"', index.InvalidHTMLAttributeValue),
            ("=false", index.InvalidHTMLAttributeValue),
        ],
    )
    def test_html_core_metadata(
        self,
        attr_value: str,
        json_value: bool | dict[str, str] | type[index.IndexServerException],
    ) -> None:
        given = f"""
            <html>
            <body>
                <a
                    href="https://files.pythonhosted.org/spam/spam-1.0.tar.gz"
                    data-core-metadata{attr_value}
                >
                        spam-1.0.tar.gz
                </a>
            </body>
            </html>
        """
        if is_exception(json_value):
            with pytest.raises(json_value):
                index.parse_details(HTML_CONTENT_TYPE, given, name="spam")
        else:
            expect: index.RawProjectDetails = typing.cast(
                "index.RawProjectDetails",
                {
                    "meta": {"api-version": "1.0"},
                    "name": "spam",
                    "files": [
                        {
                            "filename": "spam-1.0.tar.gz",
                            "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                            "hashes": {},
                            "core-metadata": json_value,
                            "dist-info-metadata": json_value,
                        }
                    ],
                },
            )
            result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

            assert result == expect

    @pytest.mark.parametrize(
        ("attr_value", "json_value"),
        [
            ("=true", True),
            ("", True),  # Spec doesn't say this is correct, but it's unambiguous.
            ('="sha256=12345abcde"', {"sha256": "12345abcde"}),
            ('="SHA256=12345abcde"', {"sha256": "12345abcde"}),
            ("=false", index.InvalidHTMLAttributeValue),
        ],
    )
    def test_html_dist_info_metadata(
        self,
        attr_value: str,
        json_value: bool | dict[str, str] | type[index.IndexServerException],
    ) -> None:
        given = f"""
            <html>
            <body>
                <a
                    href="https://files.pythonhosted.org/spam/spam-1.0.tar.gz"
                    data-dist-info-metadata{attr_value}
                >
                        spam-1.0.tar.gz
                </a>
            </body>
            </html>
        """
        if is_exception(json_value):
            with pytest.raises(json_value):
                index.parse_details(HTML_CONTENT_TYPE, given, name="spam")
        else:
            expect: index.RawProjectDetails = typing.cast(
                "index.RawProjectDetails",
                {
                    "meta": {"api-version": "1.0"},
                    "name": "spam",
                    "files": [
                        {
                            "filename": "spam-1.0.tar.gz",
                            "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                            "hashes": {},
                            "dist-info-metadata": json_value,
                            "core-metadata": json_value,
                        }
                    ],
                },
            )
            result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

            assert result == expect

    @pytest.mark.parametrize(
        ("attr_value", "json_value"),
        [
            ("=true", True),
            ("=false", False),
            ("", index.InvalidHTMLAttributeValue),
            ('="https://example.com"', index.InvalidHTMLAttributeValue),
        ],
    )
    def test_html_gpg_sig(self, attr_value: str, json_value: bool) -> None:
        given = f"""
            <html>
            <body>
                <a
                    href="https://files.pythonhosted.org/spam/spam-1.0.tar.gz"
                    data-gpg-sig{attr_value}
                >
                        spam-1.0.tar.gz
                </a>
            </body>
            </html>
        """
        if is_exception(json_value):
            with pytest.raises(json_value):
                index.parse_details(HTML_CONTENT_TYPE, given, name="spam")
        else:
            expect: index.RawProjectDetails = {
                "meta": {"api-version": "1.0"},
                "name": "spam",
                "files": [
                    {
                        "filename": "spam-1.0.tar.gz",
                        "url": "https://files.pythonhosted.org/spam/spam-1.0.tar.gz",
                        "hashes": {},
                        "gpg-sig": json_value,
                    }
                ],
            }
            result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

            assert result == expect

    @pytest.mark.parametrize(
        ("data_value", "specifier_value"),
        [
            ('="==3.16"', "==3.16"),
            ('="&gt;=3"', ">=3"),
            ("", index.InvalidHTMLAttributeValue),
        ],
    )
    def test_html_requires_python(
        self, data_value: str, specifier_value: str | type[index.IndexServerException]
    ) -> None:
        given = f"""
            <html>
            <body>
            <a
                href="https://example.com/spam/spam-1.0.tar.gz"
                data-requires-python{data_value}
            >spam-1.0.tar.gz</a>
            </body>
            </html>
        """
        if is_exception(specifier_value):
            with pytest.raises(specifier_value):
                index.parse_details(HTML_CONTENT_TYPE, given, name="spam")
        else:
            expect: index.RawProjectDetails = typing.cast(
                "index.RawProjectDetails",
                {
                    "meta": {"api-version": "1.0"},
                    "name": "spam",
                    "files": [
                        {
                            "filename": "spam-1.0.tar.gz",
                            "url": "https://example.com/spam/spam-1.0.tar.gz",
                            "hashes": {},
                            "requires-python": specifier_value,
                        }
                    ],
                },
            )
            result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

            assert result == expect

    @pytest.mark.parametrize(
        ("attr", "value"), [("", True), ('=""', True), ('="bad"', "bad")]
    )
    def test_html_yanked(self, attr: str, value: str) -> None:
        given = f"""
            <html>
            <body>
            <a
                href="https://example.com/spam/spam-1.0.tar.gz"
                data-yanked{attr}
            >spam-1.0.tar.gz</a>
            </body>
            </html>
        """
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": "https://example.com/spam/spam-1.0.tar.gz",
                    "hashes": {},
                    "yanked": value,
                }
            ],
        }
        result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

        assert result == expect

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            (
                '="https://example.com/spam/provenance"',
                "https://example.com/spam/provenance",
            ),
            ("", index.InvalidHTMLAttributeValue),
        ],
    )
    def test_html_provenance(
        self, attr: str, value: str | type[index.IndexServerException]
    ) -> None:
        given = f"""
            <html>
            <body>
            <a
                href="https://example.com/spam/spam-1.0.tar.gz"
                data-provenance{attr}
            >spam-1.0.tar.gz</a>
            </body>
            </html>
        """
        if is_exception(value):
            with pytest.raises(value):
                index.parse_details(HTML_CONTENT_TYPE, given, name="spam")
        else:
            expect: index.RawProjectDetails = typing.cast(
                "index.RawProjectDetails",
                {
                    "meta": {"api-version": "1.0"},
                    "name": "spam",
                    "files": [
                        {
                            "filename": "spam-1.0.tar.gz",
                            "url": "https://example.com/spam/spam-1.0.tar.gz",
                            "hashes": {},
                            "provenance": value,
                        }
                    ],
                },
            )
            result = index.parse_details(HTML_CONTENT_TYPE, given, name="spam")

            assert result == expect

    @pytest.mark.parametrize(
        ("content_type", "data", "args"),
        [
            (
                index.ACCEPT_JSON_V1,
                '{"meta": {"api-version": "1.0"}, "name": "Spam_Spam", "files": []}',
                {"name": "Spam-SPAM"},
            ),
            (HTML_CONTENT_TYPE, "", {"name": "Spam_Spam"}),
            (
                HTML_CONTENT_TYPE,
                "",
                {"request_url": "https://pypi.org/simple/Spam_Spam/"},
            ),
        ],
    )
    def test_normalized_name(
        self, content_type: str, data: str, args: dict[str, str]
    ) -> None:
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam-spam",
            "files": [],
        }
        result = index.parse_details(content_type, data, **args)

        assert result == expect

    @pytest.mark.parametrize(
        ("request_url", "href", "url"),
        [
            (
                "https://pypi.org/simple/spam/",
                "spam-1.0.tar.gz",
                "https://pypi.org/simple/spam/spam-1.0.tar.gz",
            ),
            (
                "https://example.com/simple/spam/",
                "https://pypi.org/simple/spam/spam-1.0.tar.gz",
                "https://pypi.org/simple/spam/spam-1.0.tar.gz",
            ),
        ],
    )
    def test_html_relative_url(self, request_url: str, href: str, url: str) -> None:
        given = f"""
                    <html>
                    <body>
                    <a
                        href="{href}"
                    >spam-1.0.tar.gz</a>
                    </body>
                    </html>
                """
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": url,
                    "hashes": {},
                }
            ],
        }
        result = index.parse_details(HTML_CONTENT_TYPE, given, request_url=request_url)

        assert result == expect

    def test_html_base_tag(self) -> None:
        given = """
            <html>
            <head>
                <base href="https://pypi.org/simple/spam/" />
                <!-- For test coverage -->
                <base />
                <base ignore="me">
            <body>
            <a
                href="spam-1.0.tar.gz"
            >spam-1.0.tar.gz</a>
            </body>
            </html>
        """
        expect: index.RawProjectDetails = {
            "meta": {"api-version": "1.0"},
            "name": "spam",
            "files": [
                {
                    "filename": "spam-1.0.tar.gz",
                    "url": "https://pypi.org/simple/spam/spam-1.0.tar.gz",
                    "hashes": {},
                }
            ],
        }
        result = index.parse_details(
            HTML_CONTENT_TYPE, given, request_url="https://example.com/simple/spam/"
        )

        assert result == expect

    @pytest.mark.parametrize("bad_value", ["", None])
    def test_name_or_request_url_provided(self, bad_value: str | None) -> None:
        with pytest.raises(TypeError):
            index.parse_details(
                HTML_CONTENT_TYPE,
                "",
                name=bad_value,  # type: ignore[arg-type]
                request_url=bad_value,
            )
