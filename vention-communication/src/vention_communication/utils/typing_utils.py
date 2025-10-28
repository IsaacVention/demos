# src/vention_communication/utils/typing_utils.py

import inspect
from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    Type,
    get_type_hints,
    _GenericAlias,
    Union,
)
from pydantic import BaseModel
from .errors import TypingError


# Sentinel type for “no request body” or “no response body”
class _Empty:
    """
    Internal marker type for “empty” request or response.
    Will map to google.protobuf.Empty in codegen.
    """

    pass


Empty = _Empty  # alias exposed for internal use


def get_input_type(fn: Callable[..., Awaitable[Any]]) -> Type[Any]:
    """
    Inspect the async function to determine the input (request) type.
    If no parameter (other than self/cls) is present, returns Empty.
    Raises TypingError if unable to resolve an annotated type.
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())

    # Drop 'self' or 'cls' if present
    if params and params[0].name in ("self", "cls"):
        params = params[1:]

    if not params:
        # No user parameter → treat as empty request
        return Empty

    # Take first parameter
    first = params[0]
    hints = get_type_hints(fn)
    if first.name not in hints:
        raise TypingError(
            f"@action: parameter '{first.name}' of function '{fn.__name__}' lacks type annotation"
        )

    input_type = hints[first.name]
    return input_type


def get_return_type(fn: Callable[..., Awaitable[Any]]) -> Type[Any]:
    """
    Inspect the async function to determine the return (response) type.
    If return annotation is None or absent → returns Empty.
    Raises TypingError if ambiguous / unsupported annotation.
    """
    hints = get_type_hints(fn)
    ret = hints.get("return", None)

    if ret is None or ret is Any:
        # No explicit annotation or generic → treat as empty response
        return Empty

    if ret is type(None):  # annotated `-> None`
        return Empty

    return ret


def is_pydantic_model(tp: Type[Any]) -> bool:
    """Returns True if tp is a subclass of pydantic.BaseModel."""
    try:
        return issubclass(tp, BaseModel)
    except Exception:
        return False
