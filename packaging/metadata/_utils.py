from collections.abc import Iterable
from typing import Any, List


def as_str(inp: Any) -> str:
    if not isinstance(inp, str):
        raise ValueError("Must be a str")
    return inp


def as_list_str(inp: Any) -> List[str]:
    if not isinstance(inp, Iterable):
        raise ValueError("Must be a list of str")
    results = []
    for entry in inp:
        if not isinstance(entry, str):
            raise ValueError("Must a list of str")
        results.append(entry)
    return results
