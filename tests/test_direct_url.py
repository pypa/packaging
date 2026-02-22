from __future__ import annotations

import pytest

from packaging.direct_url import (
    ArchiveInfo,
    DirectUrl,
    DirectUrlValidationError,
    DirInfo,
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
