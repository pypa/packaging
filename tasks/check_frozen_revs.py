#!/usr/bin/env -S uv run --script

# /// script
# dependencies = ["ruamel.yaml", "aiohttp"]
# ///

from __future__ import annotations

import argparse
import asyncio
import os
import re
from pathlib import Path
from typing import Any

import aiohttp  # type: ignore[import-not-found]
from ruamel.yaml import YAML  # type: ignore[import-not-found]

FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FROZEN_RE = re.compile(r"frozen:\s*(\S+)")
GH_REPO_RE = re.compile(r"^https://github.com/([^/]+)/([^/]+?)(?:\.git)?$")

# Accept https, ssh, .git suffix, trailing slashes, etc.
GH_URL_RE = re.compile(
    r"""
    (?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)
    (?P<owner>[^/]+)
    /
    (?P<repo>[^/]+?)(?:\.git)?
    /?$
    """,
    re.VERBOSE,
)


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
        tag,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    stdout, _ = await proc.communicate()

    if proc.returncode != 0:
        return None

    lines = [
        line.strip().split() for line in stdout.decode().splitlines() if line.strip()
    ]

    if not lines:
        return None

    # Prefer dereferenced annotated tag
    for sha, ref in lines:
        if ref.endswith("^{}"):
            return sha

    # Fallback: lightweight tag
    return lines[0][0]


async def resolve_tag_via_gh_api(
    session: aiohttp.ClientSession, repo_url: str, tag: str
) -> str | None:
    """
    Resolve tag via GitHub's tag reference API (fully async).
    Works for both lightweight and annotated tags.
    """
    m = GH_URL_RE.match(repo_url)
    if not m:
        print(f"[debug] Not a GitHub repo URL: {repo_url}")
        return None

    owner, repo = m.group("owner"), m.group("repo")
    url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/tags/{tag}"

    headers = {
        "User-Agent": "frozen-rev-validator",
        "Accept": "application/vnd.github+json",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with session.get(url, headers=headers) as resp:
            match resp.status:
                case 404:
                    print(f"[debug] Tag {tag!r} not found at {url}")
                    return None
                # Friendly message on rate limiting
                case 403 if resp.headers.get("X-RateLimit-Remaining") == "0":
                    reset = resp.headers.get("X-RateLimit-Reset")
                    print(
                        "[debug] GitHub API rate limit exceeded;"
                        " set GITHUB_TOKEN to increase limits."
                        + (f" Resets at epoch {reset}." if reset else "")
                    )
                    return None
                case _:
                    resp.raise_for_status()
                    data = await resp.json()

        obj = data.get("object")
        if not obj:
            print("[debug] No 'object' field in tag response")
            return None

        sha: str

        if obj["type"] == "tag":
            # Annotated tag → follow the tag object to get the commit SHA
            tag_url = obj["url"]
            print(f"[debug] Dereferencing annotated tag via {tag_url}")
            async with session.get(tag_url, headers=headers) as resp2:
                resp2.raise_for_status()
                tag_obj = await resp2.json()
                sha = tag_obj.get("object", {}).get("sha")
            return sha

        # Lightweight tag → already points to commit
        sha = obj.get("sha")

    except aiohttp.ClientResponseError as e:
        print(f"[debug] HTTP error from {url}: {e.status} {e.message}")
        return None
    except aiohttp.ClientError as e:
        print(f"[debug] aiohttp error contacting {url}: {e}")
        return None
    else:
        return sha


async def validate_repo(session: aiohttp.ClientSession, repo_node: Any) -> list[str]:
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
        tag_sha = await resolve_tag_via_gh_api(session, repo, tag)
        if tag_sha is None:
            errors.append(f"{repo}: release tag {tag!r} not found with GitHub API")
            return errors
        if tag_sha != rev:
            errors.append(f"{repo}: tag {tag!r} resolves to {tag_sha}, expected {rev}")

    return errors


async def main_async(repos: Any) -> int:
    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [validate_repo(session, repo) for repo in repos]
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
        help="File to validate (default: .pre-commit-config.yaml)",
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
