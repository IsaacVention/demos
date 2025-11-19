from __future__ import annotations
import inspect
from typing import Any, Callable, Optional, Type, get_type_hints, cast

from pydantic import BaseModel, ConfigDict


class TypingError(Exception):
    """Raised when type inference fails."""


def _strip_self(params: list[inspect.Parameter]) -> list[inspect.Parameter]:
    if not params:
        return params
    first = params[0]
    if first.name in ("self", "cls"):
        return params[1:]
    return params


def infer_input_type(function: Callable[..., Any]) -> Optional[Type[Any]]:
    """Infer the input type annotation from a function's first parameter.

    Args:
        function: Function to inspect

    Returns:
        Type annotation of the first parameter, or None if no parameters or type is Any

    Raises:
        TypingError: If the first parameter lacks a type annotation
    """
    signature = inspect.signature(function)
    parameters = _strip_self(list(signature.parameters.values()))
    if not parameters:
        return None

    first_param = parameters[0]
    type_hints = get_type_hints(function)
    if first_param.name not in type_hints:
        raise TypingError(f"First parameter '{first_param.name}' must be annotated")

    hint_type = type_hints[first_param.name]
    if hint_type is Any:
        return None

    if isinstance(hint_type, type):
        return cast(Type[Any], hint_type)

    return None


def infer_output_type(function: Callable[..., Any]) -> Optional[Type[Any]]:
    """Infer the return type annotation from a function.

    Args:
        function: Function to inspect

    Returns:
        Return type annotation, or None if not annotated or type is Any
    """
    type_hints = get_type_hints(function)
    return_type = type_hints.get("return")
    if return_type is None or return_type is Any:
        return None

    if isinstance(return_type, type) and return_type in (type(None),):
        return None

    if isinstance(return_type, type):
        return cast(Type[Any], return_type)

    return None


def is_pydantic_model(type_annotation: Any) -> bool:
    """Check if a type annotation is a Pydantic BaseModel.

    Args:
        type_annotation: Type to check

    Returns:
        True if the type is a Pydantic BaseModel subclass, False otherwise
    """
    try:
        return isinstance(type_annotation, type) and issubclass(
            type_annotation, BaseModel
        )
    except Exception:
        return False


def camelize(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def apply_aliases(model_cls: Type[BaseModel]) -> None:
    # Ensure Pydantic accepts both snake_case and camelCase
    existing_config = getattr(model_cls, "model_config", None)
    if existing_config is None:
        existing_dict: dict[str, Any] = {}
    else:
        existing_dict = (
            dict(existing_config) if isinstance(existing_config, dict) else {}
        )

    merged_config: dict[str, Any] = {
        "populate_by_name": True,
        "from_attributes": True,
        **existing_dict,
    }
    model_cls.model_config = cast(ConfigDict, merged_config)

    # Force rebuild first to ensure model is in a consistent state
    model_cls.model_rebuild(force=True)

    # Set aliases AFTER rebuild, as rebuild recreates fields from annotations
    fields = model_cls.model_fields
    for name, field in fields.items():
        alias = camelize(name)
        field.alias = alias
        field.validation_alias = alias
