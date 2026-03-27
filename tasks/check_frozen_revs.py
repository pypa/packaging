#!/usr/bin/env -S uv run --script

# /// script
# dependencies = ["ruamel.yaml"]
# ///

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML  # type: ignore[import-not-found]

FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FROZEN_RE = re.compile(r"frozen:\s*(\S+)")


yaml = YAML(typ="rt")  # round-trip to preserve comments


def extract_frozen_tag(repo_node: Any) -> str | None:
    if "rev" not in repo_node:
        return None
    rev_token = repo_node.ca.items.get("rev")
    if not rev_token:
        return None
    comment_token = rev_token[2]
    if not comment_token:
        return None
    m = FROZEN_RE.search(comment_token.value)
    return m.group(1) if m else None


async def resolve_tag_via_git(repo: str, tag: str) -> str | None:
    """
    Resolve tag to commit SHA using ls-remote.
    Handles annotated tags via ^{}.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "ls-remote",
        "--tags",
        repo,
        tag,  # non-annotated tag
        f"{tag}^{{}}",  # annotated tag
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    stdout, _ = await proc.communicate()

    if proc.returncode != 0:
        return None

    lines = [
        sline.split()
        for line in stdout.decode().splitlines()
        if (sline := line.strip())
    ]

    if not lines:
        return None

    # Prefer dereferenced annotated tag
    for sha, ref in lines:
        if ref.endswith("^{}"):
            return sha

    # Fallback: lightweight tag
    return lines[0][0]


async def validate_repo(repo_node: Any) -> list[str]:
    errors: list[str] = []

    repo = repo_node.get("repo")
    rev = repo_node.get("rev")

    if not repo or not rev:
        return errors

    if not FULL_SHA_RE.fullmatch(rev):
        errors.append(f"{repo}: rev '{rev}' is not a full 40-char SHA")
        return errors

    tag = extract_frozen_tag(repo_node)
    if not tag:
        return errors  # not frozen

    tag_sha = await resolve_tag_via_git(repo, tag)

    if tag_sha is None:
        errors.append(f"{repo}: release tag {tag!r} not found on GitHub")
        return errors

    if tag_sha != rev:
        errors.append(f"{repo}: tag {tag!r} resolves to {tag_sha}, expected {rev}")

    return errors


async def main_async(repos: Any) -> int:
    tasks = [validate_repo(repo) for repo in repos]
    results = await asyncio.gather(*tasks)
    errors = [err for group in results for err in group]

    if errors:
        print("Frozen rev validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate frozen revs in pre-commit config files"
    )
    parser.add_argument(
        "file",
        type=Path,
        help="File to validate (path to .pre-commit-config.yaml)",
    )
    args = parser.parse_args()
    path = args.file
    if not path.exists():
        return 2

    data = yaml.load(path)
    repos = data.get("repos", [])
    return asyncio.run(main_async(repos))


if __name__ == "__main__":
    raise SystemExit(main())
