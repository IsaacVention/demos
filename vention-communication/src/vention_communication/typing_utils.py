# typing_utils.py

from __future__ import annotations
import inspect
from typing import Any, Optional, Type, get_type_hints

from pydantic import BaseModel


class TypingError(Exception):
    pass


def _strip_self(params: list[inspect.Parameter]) -> list[inspect.Parameter]:
    if not params:
        return params
    first = params[0]
    if first.name in ("self", "cls"):
        return params[1:]
    return params


def infer_input_type(fn: Any) -> Optional[Type[Any]]:
    sig = inspect.signature(fn)
    params = _strip_self(list(sig.parameters.values()))
    if not params:
        return None  # Empty
    p0 = params[0]
    hints = get_type_hints(fn)
    if p0.name not in hints:
        raise TypingError(f"First parameter '{p0.name}' must be annotated")
    return hints[p0.name]  # type: ignore[return-value]


def infer_output_type(fn: Any) -> Optional[Type[Any]]:
    hints = get_type_hints(fn)
    rtn = hints.get("return")
    if rtn is None or rtn is Any:
        return None
    return rtn  # type: ignore[return-value]


def is_pydantic_model(tp: Any) -> bool:
    try:
        return isinstance(tp, type) and issubclass(tp, BaseModel)
    except Exception:
        return False
