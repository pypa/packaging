Direct URLs
===========

.. currentmodule:: packaging.direct_url

Parse and validate `direct_url.json files <https://packaging.python.org/en/latest/specifications/direct-url/>`_.

Usage
-----

.. code-block:: python

    import json
    from pathlib import Path

    from packaging.direct_url import ArchiveInfo, DirectUrl, DirInfo, VcsInfo

    # A VCS direct URL
    vcs_direct_url = DirectUrl(
        url="https://git.example.com/repo.git",
        vcs_info=VcsInfo(
            vcs="git",
            commit_id="2df7bdd8dfef7b879390b9fc4016f02af2f118d4",
            requested_revision="1.1.0",
        ),
    )

    # An archive direct URL
    archive_direct_url = DirectUrl(
        url="https://example.com/archive.tar.gz",
        archive_info=ArchiveInfo(
            hashes={
                "sha256": "dc321a1c18a37b5438424ef3714524229dab5f4f78b297671359426fef51be6c"
            }
        ),
    )

    # A local editable direct URL
    archive_direct_url = DirectUrl(
        url="file:///home/project/example",
        dir_info=DirInfo(
            editable=True,
        ),
    )

    # Serialization to JSON
    Path("/tmp/direct_url.json").write_text(
        json.dumps(vcs_direct_url.to_dict()), encoding="utf-8"
    )

    # Load from JSON. The resulting DirectUrl object is validated against the
    # specification, else a DirectUrlalidationError is raised
    direct_url = DirectUrl.from_dict(
        json.loads(Path("/tmp/direct_url.json").read_text(encoding="utf-8"))
    )

    # You can validate a manually constructed DirectUrl class
    vcs_direct_url.validate()


Reference
---------

.. autoclass:: DirectUrl
    :members: from_dict, to_dict, validate
    :exclude-members: __init__, __new__

.. class:: ArchiveInfo

.. class:: DirInfo

.. class:: VcsInfo

The following exception may be raised by this module:

.. autoexception:: DirectUrlValidationError
    :exclude-members: __init__, __new__
