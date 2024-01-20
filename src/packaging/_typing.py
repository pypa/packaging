import sys
import typing

if sys.version_info[:2] >= (3, 8):  # pragma: no cover
    from typing import Literal
elif typing.TYPE_CHECKING:  # pragma: no cover
    from typing_extensions import Literal
else:  # pragma: no cover
    try:
        from typing_extensions import Literal
    except ImportError:

        class Literal:
            def __init_subclass__(*_args, **_kwargs):
                pass


if sys.version_info[:2] >= (3, 9):  # pragma: no cover
    from typing import TypedDict
elif typing.TYPE_CHECKING:  # pragma: no cover
    from typing_extensions import TypedDict
else:  # pragma: no cover
    try:
        from typing_extensions import TypedDict
    except ImportError:

        class TypedDict:
            def __init_subclass__(*_args, **_kwargs):
                pass


__all__ = [
    "Literal",
    "TypedDict",
]
