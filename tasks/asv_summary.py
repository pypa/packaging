"""Convert ``asv continuous`` output into a compact Markdown summary.

Usage: ``python asv_summary.py asv_output.txt >> "$GITHUB_STEP_SUMMARY"``

With ``--comment-dir DIR``, also write ``DIR/comment.md`` (the summary without
the full asv output) and ``DIR/significant`` (``true`` or ``false``).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKS = {
    "+": "🔴",  # Slower
    "-": "🟢",  # Faster
    "!": "❌",  # New failure
    "*": "✅",  # Fixed failure
    "x": "⚪",  # Not comparable
}
SIGNIFICANT = frozenset("+-!*")

ROW = re.compile(
    r"^\|\s*(?P<mark>\S?)\s*\|[^|]*\|[^|]*\|\s*(?P<ratio>[^|]*?)\s*"
    r"\|\s*(?P<name>[^|]+?)\s+\[[^\]]*-py(?P<python>\d+\.\d+t?)[^\]]*\]\s*\|$"
)
HEADER = re.compile(
    r"Before \[(?P<before>\w+)\](?: <(?P<ref>[^>]+)>)?\s*\|\s*After \[(?P<after>\w+)\]"
)


def clean_name(name: str) -> str:
    """Turn ``module.Class.time_method(param)`` into ``module: method(param)``."""
    base, paren, params = name.partition("(")
    module, _, method = base.rpartition(".")
    module = module.split(".")[0]
    method = method.removeprefix("time_")
    return f"{module}: {method}{paren}{params}"


def format_ratio(ratio: str) -> str:
    """Pad ratios to two decimals, since asv strips trailing zeros."""
    prefix = "~" if ratio.startswith("~") else ""
    try:
        return f"{prefix}{float(ratio.lstrip('~')):.2f}"
    except ValueError:
        return ratio or "n/a"


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.rstrip("t").split("."))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Output of asv continuous.")
    parser.add_argument("--comment-dir", type=Path, help="Write PR comment files.")
    args = parser.parse_args()

    text = args.path.read_text(encoding="utf-8")
    _, _, table = text.partition("All benchmarks:")
    lines = table.strip().splitlines()

    results: dict[str, dict[str, str]] = {}
    significant = False
    for line in lines:
        if not (m := ROW.match(line.strip())):
            continue
        significant |= m["mark"] in SIGNIFICANT
        ratio = format_ratio(m["ratio"])
        cell = f"{MARKS[m['mark']]} **{ratio}**" if m["mark"] in MARKS else ratio
        results.setdefault(clean_name(m["name"]), {})[m["python"]] = cell

    out = []
    if header := HEADER.search(table):
        ref = f" ({header['ref']})" if header["ref"] else ""
        out += [f"## Benchmarks: `{header['before']}`{ref} → `{header['after']}`", ""]
    else:
        out += ["## Benchmarks", ""]

    status = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("|")]
    if status:
        out += [f"**{status[-1].strip()}**", ""]

    if results:
        cols = sorted({p for row in results.values() for p in row}, key=version_key)
        out += [
            "Ratio of after / before time (lower is faster). "
            "🔴 slower, 🟢 faster, ❌ newly failing, ✅ fixed, ⚪ not comparable, "
            "`~` exceeds threshold but not statistically significant.",
            "",
            "| Benchmark | " + " | ".join(cols) + " |",
            "|:--|" + "--:|" * len(cols),
        ]
        for name, row in sorted(results.items()):
            cells = " | ".join(row.get(c, "") for c in cols)
            out.append(f"| {name} | {cells} |")
    else:
        out.append("No benchmark results found.")

    summary = "\n".join(out)
    print(summary)
    if results:
        print("\n<details><summary>Full asv output</summary>\n")
        print("\n".join(lines))
        print("\n</details>")

    if args.comment_dir:
        args.comment_dir.mkdir(parents=True, exist_ok=True)
        (args.comment_dir / "comment.md").write_text(summary + "\n", encoding="utf-8")
        flag = "true" if significant else "false"
        (args.comment_dir / "significant").write_text(flag + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
