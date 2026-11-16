from __future__ import annotations

import copy
import dataclasses
import pickle
from typing import Any

import pytest

from packaging.direct_url import (
    ArchiveInfo,
    DirectUrl,
    DirectUrlValidationError,
    DirInfo,
    VcsInfo,
    _strip_url,
)


@pytest.mark.parametrize(
    "direct_url_dict",
    [
        {
            "url": "file:///projects/myproject",
            "dir_info": {},
        },
        {
            "url": "file:///projects/myproject",
            "dir_info": {"editable": True},
        },
        {
            "url": "file:///projects/myproject",
            "dir_info": {"editable": False},
        },
        {
            "url": "https://example.com/archive.zip",
            "archive_info": {
                "hashes": {"sha256": "f" * 40},
            },
        },
        {
            "url": "https://g.c/user/repo.git",
            "vcs_info": {
                "vcs": "git",
                "commit_id": "a" * 40,
                "requested_revision": "main",
            },
        },
    ],
)
def test_direct_url_round_trips(direct_url_dict: dict[str, object]) -> None:
    assert DirectUrl.from_dict(direct_url_dict).to_dict() == direct_url_dict


def test_legacy_hash_populates_hashes() -> None:
    direct_url = DirectUrl.from_dict(
        {
            "url": "https://example.com/archive.zip",
            "archive_info": {
                "hash": "sha256=" + "f" * 40,
            },
        }
    )
    assert direct_url.archive_info
    assert direct_url.archive_info.hashes == {"sha256": "f" * 40}


def test_to_dict_generate_legacy_hash() -> None:
    direct_url = DirectUrl(
        url="https://example.com/archive.zip",
        archive_info=ArchiveInfo(hashes={"sha256": "f" * 40}),
    )
    assert "hash" not in direct_url.to_dict()["archive_info"]
    assert (
        direct_url.to_dict(generate_legacy_hash=True)["archive_info"]["hash"]
        == "sha256=" + "f" * 40
    )


def test_to_dict_generate_legacy_hash_no_hashes() -> None:
    direct_url = DirectUrl(
        url="https://example.com/archive.zip",
        archive_info=ArchiveInfo(),
    )
    assert "hash" not in direct_url.to_dict(generate_legacy_hash=True)["archive_info"]


def test_to_dict_generate_legacy_hash_multiple_hashes() -> None:
    direct_url = DirectUrl(
        url="https://example.com/archive.zip",
        archive_info=ArchiveInfo(hashes={"sha256": "f" * 40, "md5": "1" * 32}),
    )
    assert (
        direct_url.to_dict(generate_legacy_hash=True)["archive_info"]["hash"]
        == "sha256=" + "f" * 40
    )


def test_validate_archive_info_hashes() -> None:
    with pytest.raises(
        DirectUrlValidationError,
        match=r"Hash values must be strings in 'archive_info.hashes'",
    ):
        DirectUrl.from_dict(
            {
                "url": "https://example.com/archive.zip",
                "archive_info": {
                    "hashes": {"md5": 12345},
                },
            }
        )


def test_validate_archive_info_hash_invalid_format() -> None:
    with pytest.raises(
        DirectUrlValidationError,
        match=(
            r"Invalid hash format \(expected '<algorithm>=<hash>'\) "
            r"in 'archive_info.hash'"
        ),
    ):
        DirectUrl.from_dict(
            {
                "url": "https://example.com/archive.zip",
                "archive_info": {
                    "hash": "md5:12345",
                },
            }
        )


def test_validate_archive_info_hash_missing_in_hashes() -> None:
    with pytest.raises(
        DirectUrlValidationError,
        match=r"Algorithm 'md5' used in hash field is not present in hashes field",
    ):
        DirectUrl.from_dict(
            {
                "url": "https://example.com/archive.zip",
                "archive_info": {
                    "hashes": {"sha256": "f" * 40},
                    "hash": "md5=12345",
                },
            }
        )


def test_validate_archive_info_hash_different_in_hashes() -> None:
    with pytest.raises(
        DirectUrlValidationError,
        match=(
            r"Algorithm 'md5' used in hash field has different value in hashes field "
            r"in 'archive_info.hash'"
        ),
    ):
        DirectUrl.from_dict(
            {
                "url": "https://example.com/archive.zip",
                "archive_info": {
                    "hashes": {"md5": "123456"},
                    "hash": "md5=12345",
                },
            }
        )


def test_validate_archive_info_hash_same_in_hashes() -> None:
    DirectUrl.from_dict(
        {
            "url": "https://example.com/archive.zip",
            "archive_info": {
                "hashes": {"md5": "123456"},
                "hash": "md5=123456",
            },
        }
    )


@pytest.mark.parametrize(
    "direct_url_dict",
    [
        {
            "url": "file:///projects/myproject",
        },
        {
            "url": "https://example.com/archive.zip",
            "archive_info": {},
            "dir_info": {},
        },
        {
            "url": "https://g.c/user/repo.git",
            "vcs_info": {
                "vcs": "git",
                "commit_id": "a" * 40,
            },
            "archive_info": {},
        },
    ],
)
def test_one_info_field(direct_url_dict: dict[str, object]) -> None:
    with pytest.raises(
        DirectUrlValidationError,
        match=r"Exactly one of vcs_info, archive_info, dir_info must be present",
    ):
        DirectUrl.from_dict(direct_url_dict)


def test_dir_info_url_scheme_file() -> None:
    DirectUrl.from_dict(
        {
            "url": "file:///home/myproject",
            "dir_info": {},
        }
    )
    with pytest.raises(
        DirectUrlValidationError,
        match=r"URL scheme must be file:// when dir_info is present",
    ):
        DirectUrl.from_dict(
            {
                "url": "https://example.com/projects/myproject",
                "dir_info": {},
            }
        )


@pytest.mark.parametrize(
    "url",
    [
        "FILE:///home/myproject",
        "File:///home/myproject",
        "file:/home/myproject",
        "file://localhost/home/myproject",
    ],
)
def test_dir_info_url_file_absolute_case_insensitive(url: str) -> None:
    """Per RFC 3986 §3.1, URL schemes are case-insensitive; all variants of
    absolute file URLs must be accepted when dir_info is present."""
    DirectUrl.from_dict({"url": url, "dir_info": {}})


@pytest.mark.parametrize(
    "url",
    [
        "file:relative",
        "file:./relative",
        "file:",
        "file://relative",
        "file://localhost",
    ],
)
def test_dir_info_url_requires_absolute_file_url(url: str) -> None:
    with pytest.raises(
        DirectUrlValidationError,
        match=r"File URL must be absolute when dir_info is present",
    ):
        DirectUrl.from_dict({"url": url, "dir_info": {}})


def test_missing_url() -> None:
    with pytest.raises(
        DirectUrlValidationError,
        match=r"Missing required value in 'url'",
    ):
        DirectUrl.from_dict(
            {
                "dir_info": {},
            }
        )


def test_commit_id_type() -> None:
    with pytest.raises(
        DirectUrlValidationError,
        match=r"Unexpected type int \(expected str\) in 'vcs_info.commit_id'",
    ):
        DirectUrl.from_dict(
            {
                "url": "https://g.c/user/repo.git",
                "vcs_info": {"vcs": "git", "commit_id": 12345},
            }
        )


def test_validate() -> None:
    direct_url = DirectUrl(url="file:///projects/myproject", dir_info=DirInfo())
    direct_url.validate()


def test_validate_error() -> None:
    direct_url = DirectUrl(url="file:///projects/myproject")
    with pytest.raises(DirectUrlValidationError):
        direct_url.validate()


@pytest.mark.parametrize(
    ("url", "safe_user_passwords", "expected_url"),
    [
        ("https://g.c/user/repo.git", ["git"], "https://g.c/user/repo.git"),
        ("https://user:pass@g.c/user/repo.git", ["git"], "https://g.c/user/repo.git"),
        ("https://user:pa@ss@g.c/user/repo.git", ["git"], "https://g.c/user/repo.git"),
        ("ssh://git@g.c/user/repo.git", [], "ssh://g.c/user/repo.git"),
        ("ssh://git@g.c/user/repo.git", ["git"], "ssh://git@g.c/user/repo.git"),
        ("ssh://cvs@g.c/user/repo.git", ["git"], "ssh://g.c/user/repo.git"),
        ("ssh://cvs@g.c/user/repo.git", ["git", "cvs"], "ssh://cvs@g.c/user/repo.git"),
        (
            "https://${USER}:${PASSWORD}@g.c/user/repo.git",
            ["git"],
            "https://${USER}:${PASSWORD}@g.c/user/repo.git",
        ),
        (
            "https://user:${PASSWORD}@g.c/user/repo.git",
            ["git"],
            "https://g.c/user/repo.git",
        ),
        (
            "https://git:${PASSWORD}@g.c/user/repo.git",
            ["git"],
            "https://g.c/user/repo.git",
        ),
        (
            "https://${TOKEN}@g.c/user/repo.git",
            ["git"],
            "https://${TOKEN}@g.c/user/repo.git",
        ),
    ],
)
def test_strip_url(url: str, safe_user_passwords: list[str], expected_url: str) -> None:
    assert _strip_url(url, safe_user_passwords) == expected_url


def test_to_dict_strip_url() -> None:
    direct_url = DirectUrl(
        url="https://user:pass@g.c/user/repo.git",
        vcs_info=VcsInfo(vcs="git", commit_id="a" * 40),
    )
    assert direct_url.to_dict()["url"] == "https://g.c/user/repo.git"


def test_to_dict_strip_url_with_at_in_password() -> None:
    direct_url = DirectUrl(
        url="https://user:pa@ss@g.c/user/repo.git",
        vcs_info=VcsInfo(vcs="git", commit_id="a" * 40),
    )
    assert direct_url.to_dict()["url"] == "https://g.c/user/repo.git"


def test_to_dict_no_strip_url() -> None:
    direct_url = DirectUrl(
        url="https://user:pass@g.c/user/repo.git",
        vcs_info=VcsInfo(vcs="git", commit_id="a" * 40),
    )
    assert (
        direct_url.to_dict(strip_user_password=False)["url"]
        == "https://user:pass@g.c/user/repo.git"
    )


def test_to_dict_strip_url_git_safe_default() -> None:
    direct_url = DirectUrl(
        url="ssh://git@g.c/user/repo.git",
        vcs_info=VcsInfo(vcs="git", commit_id="a" * 40),
    )
    assert direct_url.to_dict()["url"] == "ssh://git@g.c/user/repo.git"


class _OldPickle:
    """Pickle as an instance of ``cls`` with ``state`` as the state."""

    def __init__(self, cls: type, state: dict[str, Any]) -> None:
        self.cls = cls
        self.state = state

    def __reduce__(self) -> tuple[Any, ...]:
        return object.__new__, (self.cls,), self.state


def _dict_state(value: object) -> object:
    """Make dataclasses (also nested ones) pickle like packaging 26.3 did,
    with the instance ``__dict__`` as the state."""
    if dataclasses.is_dataclass(value):
        state = {
            f.name: _dict_state(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
        return _OldPickle(type(value), state)
    if isinstance(value, (list, tuple)):
        return type(value)(_dict_state(v) for v in value)
    return value


_DIRECT_URLS = [
    DirectUrl(url="file:///p", dir_info=DirInfo(editable=True)),
    DirectUrl(
        url="https://e.com/a.zip",
        archive_info=ArchiveInfo(hashes={"sha256": "f" * 40}),
        subdirectory="sub",
    ),
    DirectUrl(
        url="https://g.c/r.git",
        vcs_info=VcsInfo(vcs="git", commit_id="a" * 40, requested_revision="v1"),
    ),
]


@pytest.mark.parametrize("direct_url", _DIRECT_URLS)
def test_pickle_roundtrip(direct_url: DirectUrl) -> None:
    assert pickle.loads(pickle.dumps(direct_url)) == direct_url
    assert copy.deepcopy(direct_url) == direct_url


@pytest.mark.parametrize("direct_url", _DIRECT_URLS)
def test_pickle_old_dict_state_loads(direct_url: DirectUrl) -> None:
    assert pickle.loads(pickle.dumps(_dict_state(direct_url))) == direct_url


@pytest.mark.parametrize(
    "state",
    [
        {"url": "file:///p"},
        {
            "url": "file:///p",
            "archive_info": None,
            "vcs_info": None,
            "dir_info": None,
            "subdirectory": None,
            "unknown": None,
        },
    ],
)
def test_pickle_old_dict_state_wrong_keys(state: dict[str, Any]) -> None:
    data = pickle.dumps(_OldPickle(DirectUrl, state))
    with pytest.raises(TypeError, match="DirectUrl"):
        pickle.loads(data)


# Generated with packaging==26.1 and 26.3, Python 3.13, pickle protocol 2.
_PICKLE_26_3 = (
    b"\x80\x02cpackaging.direct_url\nDirectUrl\nq\x00)\x81q\x01}q\x02(X\x03"
    b"\x00\x00\x00urlq\x03X\x11\x00\x00\x00https://g.c/r.gitq\x04X\x0c\x00"
    b"\x00\x00archive_infoq\x05NX\x08\x00\x00\x00vcs_infoq\x06cpackaging.dir"
    b"ect_url\nVcsInfo\nq\x07)\x81q\x08}q\x09(X\x03\x00\x00\x00vcsq\nX\x03"
    b"\x00\x00\x00gitq\x0bX\x09\x00\x00\x00commit_idq\x0cX\x08\x00\x00\x00aa"
    b"aaaaaaq\x0dX\x12\x00\x00\x00requested_revisionq\x0eX\x02\x00\x00\x00v1"
    b"q\x0fubX\x08\x00\x00\x00dir_infoq\x10NX\x0c\x00\x00\x00subdirectoryq"
    b"\x11Nub."
)


# Generated with packaging==26.4.dev0, Python 3.13, pickle protocol 2.
_PICKLE_26_4_DEV = (
    b"\x80\x02cpackaging.direct_url\nDirectUrl\nq\x00)\x81q\x01]q\x02(X\x11"
    b"\x00\x00\x00https://g.c/r.gitq\x03Ncpackaging.direct_url\nVcsInfo\nq"
    b"\x04)\x81q\x05]q\x06(X\x03\x00\x00\x00gitq\x07X\x08\x00\x00\x00aaaaaaa"
    b"aq\x08X\x02\x00\x00\x00v1q\x09ebNNeb."
)


@pytest.mark.parametrize(
    "data", [_PICKLE_26_3, _PICKLE_26_4_DEV], ids=["26.3", "26.4.dev0"]
)
def test_pickle_from_older_version_loads(data: bytes) -> None:
    expected = DirectUrl(
        url="https://g.c/r.git",
        vcs_info=VcsInfo(vcs="git", commit_id="a" * 8, requested_revision="v1"),
    )
    assert pickle.loads(data) == expected
