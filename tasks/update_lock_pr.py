# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Publish refreshed locks as one signed draft PR using the runner's GitHub CLI."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "ci/update-locks"
TITLE = "build(deps): refresh dependency locks"
BODY = "Refresh the locked dependencies with the seven-day upload cutoff."
COMMIT = """mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) { commit { oid } }
}"""


def run(root: Path, *command: str, payload: Mapping[str, object] | None = None) -> str:
    """Run a CLI command, propagating failures without interpreting shell text."""
    result = subprocess.run(
        command,
        cwd=root,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def same_lock(before: bytes, after: bytes, *, saved_locks_valid: bool) -> bool:
    """Compare refresh results, retaining validation repairs for stale locks."""
    if not saved_locks_valid:
        return before.strip() == after.strip()

    documents = [tomllib.loads(content.decode()) for content in (before, after)]
    for document in documents:
        provenance = document.get("tool", {}).get("nab", {})
        provenance.pop("created-at", None)
        # Re-anchoring a relative cutoff changes both input hashes.
        validation = provenance.get("validation", {})
        validation.pop("all-inputs-sha256", None)
        validation.pop("selection-inputs-sha256", None)
    return documents[0] == documents[1]


@contextlib.contextmanager
def signed_candidate(
    root: Path,
    repository: str,
    base: str,
    additions: list[dict[str, str]],
) -> Generator[str, None, None]:
    """Keep a verified candidate reachable until its caller has pushed it."""
    candidate = f"ci/lock-candidate-{uuid.uuid4().hex}"
    run(
        root,
        "gh",
        "api",
        "--method",
        "POST",
        f"repos/{repository}/git/refs",
        "--input",
        "-",
        payload={"ref": f"refs/heads/{candidate}", "sha": base},
    )
    try:
        # GitHub signs this commit without putting a private signing key on the runner.
        head = run(
            root,
            "gh",
            "api",
            "graphql",
            "--input",
            "-",
            "--jq",
            ".data.createCommitOnBranch.commit.oid",
            payload={
                "query": COMMIT,
                "variables": {
                    "input": {
                        "branch": {
                            "repositoryNameWithOwner": repository,
                            "branchName": candidate,
                        },
                        "expectedHeadOid": base,
                        "message": {"headline": TITLE},
                        "fileChanges": {"additions": additions},
                    }
                },
            },
        )
        verification = run(
            root,
            "gh",
            "api",
            f"repos/{repository}/commits/{head}",
            "--jq",
            r'.commit.verification | "\(.verified) \(.reason)"',
        )
        if verification != "true valid":
            message = f"refusing unverified update commit: {verification}"
            raise ValueError(message)
        run(root, "git", "fetch", "--no-tags", "origin", f"refs/heads/{candidate}")
        yield head
    finally:
        run(
            root,
            "gh",
            "api",
            "--method",
            "DELETE",
            f"repos/{repository}/git/refs/heads/{candidate}",
        )


def publish(root: Path, repository: str, *, saved_locks_valid: bool) -> bool:
    """Replace only the managed branch, refusing an update raced by another writer."""
    additions = []
    # Only publish lockfiles already tracked by the reviewed base.
    paths = run(
        root,
        "git",
        "ls-files",
        "--",
        ":(top,glob)pylock.*.toml",
        ":(top,glob)tasks/downstream/pylock.*.toml",
        ":(top,glob)tasks/pickle/pylock.pickle-*.toml",
    )
    for path in paths.splitlines():
        before = run(root, "git", "show", f"HEAD:{path}").encode()
        after = (root / path).read_bytes()
        if not same_lock(before, after, saved_locks_valid=saved_locks_valid):
            additions.append(
                {"path": path, "contents": base64.b64encode(after).decode()}
            )
    if not additions:
        return False

    reference = f"refs/heads/{BRANCH}"
    remote = run(root, "git", "ls-remote", "--heads", "origin", reference)
    old_head = remote.split()[0] if remote else ""
    existing = run(
        root,
        "gh",
        "api",
        "--method",
        "GET",
        f"repos/{repository}/pulls",
        "-f",
        "state=open",
        "-f",
        "base=main",
        "-f",
        f"head={repository.split('/', maxsplit=1)[0]}:{BRANCH}",
        "--jq",
        ".[].number",
    )
    base = run(root, "git", "rev-parse", "HEAD")
    with signed_candidate(root, repository, base, additions) as head:
        run(
            root,
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "credential.helper=!gh auth git-credential",
            "push",
            f"--force-with-lease={reference}:{old_head}",
            "origin",
            f"{head}:{reference}",
        )

    if not existing:
        run(
            root,
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{repository}/pulls",
            "--input",
            "-",
            payload={
                "base": "main",
                "head": BRANCH,
                "draft": True,
                "title": TITLE,
                "body": BODY,
            },
        )
    return True


def main() -> None:
    """Tell the next workflow job whether an update needs CI."""
    changed = publish(
        ROOT,
        os.environ["GH_REPO"],
        saved_locks_valid=os.environ["SAVED_LOCKS_VALID"] == "true",
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"changed={str(changed).lower()}\n")


if __name__ == "__main__":
    main()
