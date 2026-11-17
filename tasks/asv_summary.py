"""Summarize ``asv continuous`` results as a compact Markdown table.

Usage: ``python asv_summary.py BEFORE AFTER >> "$GITHUB_STEP_SUMMARY"``

This reads the asv result JSON files for the two commits. It does not use
asv's per-run significance, since one noisy Python version on a shared runner
should not flag a change. Instead, a benchmark is flagged if ``k`` Python
versions move in one direction by at least ``threshold * min_count / k``,
for some ``k >= min_count``. More versions that agree need a smaller change.
Versions that move the other way by the same amount subtract from ``k``.

With ``--comment-dir DIR``, also write ``DIR/comment.md`` and
``DIR/significant`` (``true`` or ``false``).
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

LEGEND = (
    "Ratio of after / before time (lower is faster). "
    "🔴 slower, 🟢 faster, ❌ newly failing, ✅ fixed, ⚪ not comparable "
    "(benchmark changed). "
    "Values past the threshold are bold. A row is marked only if several "
    "Python versions agree. The more versions agree, the smaller the change "
    "can be."
)


@dataclass
class Row:
    cells: dict[str, str] = field(default_factory=dict)
    changes: list[float] = field(default_factory=list)
    failed: bool = False
    fixed: bool = False


def resolve(ref: str) -> str:
    cmd = ["git", "rev-parse", ref]
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def clean_name(name: str) -> str:
    """Turn ``module.Class.time_method(param)`` into ``module: method(param)``."""
    base, paren, params = name.partition("(")
    module, _, method = base.rpartition(".")
    module = module.split(".")[0]
    method = method.removeprefix("time_")
    return f"{module}: {method}{paren}{params}"


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.rstrip("t").split("."))


Results = dict[str, tuple[float | None, str]]


def load(results_dir: Path, commit: str) -> dict[str, Results]:
    """Return ``{python: {benchmark: (time, version)}}`` for one commit."""
    out: dict[str, Results] = {}
    for path in results_dir.glob(f"*/{commit[:8]}-*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("commit_hash") != commit:
            continue
        cols = data["result_columns"]
        bench: Results = {}
        for name, row in data["results"].items():
            # Trailing empty columns may be omitted.
            entry = dict(zip(cols, row, strict=False))
            params = entry.get("params") or []
            combos = list(itertools.product(*params)) if params else [()]
            values = entry["result"] or [None] * len(combos)
            for combo, value in zip(combos, values, strict=True):
                full = f"{name}({', '.join(combo)})" if combo else name
                bench[full] = (value, entry["version"])
        out[data["python"]] = bench
    return out


def classify(changes: list[float], limit: float, min_count: int) -> int:
    """Return 1 for slower, -1 for faster, or 0. Changes are log ratios."""
    low = min(min_count, len(changes))
    for k in range(max(low, 1), len(changes) + 1):
        bar = limit * low / k
        net = sum(c >= bar for c in changes) - sum(c <= -bar for c in changes)
        if abs(net) >= k:
            return 1 if net > 0 else -1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", help="Base commit or ref.")
    parser.add_argument("after", help="Head commit or ref.")
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument(
        "--min-count",
        type=int,
        default=3,
        help="Fewest Python versions that can flag a change at --threshold.",
    )
    parser.add_argument("--comment-dir", type=Path, help="Write PR comment files.")
    args = parser.parse_args()

    before_hash, after_hash = resolve(args.before), resolve(args.after)
    before = load(args.results, before_hash)
    after = load(args.results, after_hash)
    pythons = sorted(before.keys() & after.keys(), key=version_key)
    limit = math.log1p(args.threshold)

    rows: dict[str, Row] = {}
    for py in pythons:
        for name, (new, new_version) in after[py].items():
            row = rows.setdefault(clean_name(name), Row())
            if name not in before[py]:
                row.cells[py] = "new"
                continue
            old, old_version = before[py][name]
            if old_version != new_version:
                row.cells[py] = "⚪"
            elif new is None:
                row.failed |= old is not None
                row.cells[py] = "❌" if old is not None else "failed"
            elif old is None:
                row.fixed = True
                row.cells[py] = "✅"
            else:
                change = math.log(new / old)
                row.changes.append(change)
                text = f"{new / old:.2f}"
                row.cells[py] = f"**{text}**" if abs(change) >= limit else text

    slower = faster = 0
    table = []
    for name, row in sorted(rows.items()):
        mark = ""
        direction = classify(row.changes, limit, args.min_count)
        if direction > 0:
            mark = "🔴"
            slower += 1
        elif direction < 0:
            mark = "🟢"
            faster += 1
        if row.failed:
            mark = "❌" + mark
        elif row.fixed:
            mark = "✅" + mark
        cells = " | ".join(row.cells.get(py, "") for py in pythons)
        label = f"{mark} {name}" if mark else name
        table.append(f"| {label} | {cells} |")

    failed = sum(row.failed for row in rows.values())
    significant = bool(slower or faster or failed)

    ref = "" if before_hash.startswith(args.before) else f" ({args.before})"
    out = [f"## Benchmarks: `{before_hash[:8]}`{ref} → `{after_hash[:8]}`", ""]
    if not rows:
        out.append("No benchmark results found.")
    else:
        status = [
            f"{n} {label}"
            for n, label in (
                (slower, "slower"),
                (faster, "faster"),
                (failed, "newly failing"),
            )
            if n
        ]
        out += [f"**{', '.join(status) if status else 'No significant changes'}.**", ""]
        out += [
            LEGEND,
            "",
            "| Benchmark | " + " | ".join(pythons) + " |",
            "|:--|" + "--:|" * len(pythons),
            *table,
        ]

    summary = "\n".join(out)
    print(summary)

    if args.comment_dir:
        args.comment_dir.mkdir(parents=True, exist_ok=True)
        (args.comment_dir / "comment.md").write_text(summary + "\n", encoding="utf-8")
        flag = "true" if significant else "false"
        (args.comment_dir / "significant").write_text(flag + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
