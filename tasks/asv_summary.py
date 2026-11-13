"""Convert ``asv continuous`` output into a compact Markdown summary.

Usage: ``python asv_summary.py asv_output.txt >> "$GITHUB_STEP_SUMMARY"``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKS = {
    "+": "🔴",  # Slower
    "-": "🟢",  # Faster
    "!": "❌",  # New failure
    "*": "✅",  # Fixed failure
    "x": "⚪",  # Not comparable
}

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


def main(path: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    _, _, table = text.partition("All benchmarks:")
    lines = table.strip().splitlines()

    results: dict[str, dict[str, str]] = {}
    for line in lines:
        if not (m := ROW.match(line.strip())):
            continue
        ratio = format_ratio(m["ratio"])
        cell = f"{MARKS[m['mark']]} **{ratio}**" if m["mark"] in MARKS else ratio
        results.setdefault(clean_name(m["name"]), {})[m["python"]] = cell

    if header := HEADER.search(table):
        ref = f" ({header['ref']})" if header["ref"] else ""
        print(f"## Benchmarks: `{header['before']}`{ref} → `{header['after']}`\n")
    else:
        print("## Benchmarks\n")

    status = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("|")]
    if status:
        print(f"**{status[-1].strip()}**\n")

    if not results:
        print("No benchmark results found.")
        return

    print(
        "Ratio of after / before time (lower is faster). "
        "🔴 slower, 🟢 faster, ❌ newly failing, ✅ fixed, ⚪ not comparable, "
        "`~` exceeds threshold but not statistically significant.\n"
    )
    cols = sorted({p for row in results.values() for p in row}, key=version_key)
    print("| Benchmark | " + " | ".join(cols) + " |")
    print("|:--|" + "--:|" * len(cols))
    for name, row in sorted(results.items()):
        cells = " | ".join(row.get(c, "") for c in cols)
        print(f"| {name} | {cells} |")

    print("\n<details><summary>Full asv output</summary>\n")
    print("\n".join(lines))
    print("\n</details>")


if __name__ == "__main__":
    main(sys.argv[1])
