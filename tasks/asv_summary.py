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
    cmd = ["git", "rev-parse", f"{ref}^{{commit}}"]
    return subprocess.check_output(cmd, text=True).strip()


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
            combos = list(itertools.product(*(entry.get("params") or [])))
            values = entry["result"] or [None] * len(combos)
            for combo, value in zip(combos, values, strict=True):
                full = f"{name}({', '.join(combo)})" if combo else name
                bench[full] = (value, entry["version"])
        out[data["python"]] = bench
    return out


def classify(changes: list[float], limit: float, min_count: int) -> int:
    """Return 1 for slower, -1 for faster, or 0. Changes are log ratios."""
    low = max(min_count, 1)
    for k in range(low, len(changes) + 1):
        bar = limit * low / k
        net = sum(c >= bar for c in changes) - sum(c <= -bar for c in changes)
        if abs(net) >= k:
            return 1 if net > 0 else -1
    return 0


def compare(
    before: dict[str, Results],
    after: dict[str, Results],
    pythons: list[str],
    limit: float,
) -> dict[str, Row]:
    """Return one row per benchmark, with one cell per Python version."""
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
            elif new is None and old is None:
                row.cells[py] = "failed"
            elif new is None:
                row.failed = True
                row.cells[py] = "❌"
            elif old is None:
                row.fixed = True
                row.cells[py] = "✅"
            else:
                ratio = new / old
                change = math.log(ratio)
                row.changes.append(change)
                text = f"{ratio:.2f}"
                if abs(change) >= limit:
                    dot = "🔴" if change > 0 else "🟢"
                    text = f"{dot} **{text}**"
                row.cells[py] = text
    return rows


def render(
    rows: dict[str, Row], pythons: list[str], limit: float, min_count: int
) -> tuple[list[str], bool]:
    """Return the Markdown lines and whether a benchmark is flagged."""
    if not rows:
        return ["No benchmark results found."], False

    counts = {"slower": 0, "faster": 0, "newly failing": 0, "fixed": 0}
    table = []
    for name, row in sorted(rows.items()):
        direction = classify(row.changes, limit, min_count)
        mark = "❌" if row.failed else "✅" if row.fixed else ""
        mark += {1: "🔴", -1: "🟢", 0: ""}[direction]
        counts["slower"] += direction > 0
        counts["faster"] += direction < 0
        counts["newly failing"] += row.failed
        counts["fixed"] += row.fixed
        cells = " | ".join(row.cells.get(py, "") for py in pythons)
        label = f"{mark} {name}" if mark else name
        table.append(f"| {label} | {cells} |")

    status = [f"{n} {label}" for label, n in counts.items() if n]
    lines = [
        f"**{', '.join(status) or 'No significant changes'}.**",
        "",
        LEGEND,
        "",
        "| Benchmark | " + " | ".join(pythons) + " |",
        "|:--|" + "--:|" * len(pythons),
        *table,
    ]
    return lines, bool(status)


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

    rows = compare(before, after, pythons, limit)
    lines, significant = render(rows, pythons, limit, args.min_count)

    ref = "" if before_hash.startswith(args.before) else f" ({args.before})"
    title = f"## Benchmarks: `{before_hash[:8]}`{ref} → `{after_hash[:8]}`"
    summary = "\n".join([title, "", *lines])
    print(summary)
    if not rows:
        # Fail the job, so a broken run does not replace the PR comment.
        raise SystemExit(1)

    if args.comment_dir:
        args.comment_dir.mkdir(parents=True, exist_ok=True)
        (args.comment_dir / "comment.md").write_text(summary + "\n", encoding="utf-8")
        flag = "true" if significant else "false"
        (args.comment_dir / "significant").write_text(flag + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
