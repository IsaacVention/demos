from __future__ import annotations
from typing import Any, Dict, List, Optional, Type, Union, get_args, get_origin

from .decorators import collect_bundle
from .typing_utils import is_pydantic_model
from .entries import RpcBundle, StreamEntry

_SCALAR_MAP = {
    int: "int64",
    float: "double",
    str: "string",
    bool: "bool",
}

HEADER = """syntax = "proto3";
package vention.app.v1;

import "google/protobuf/empty.proto";

"""


def _unwrap_optional(type_annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(type_annotation)
    if origin is Union:
        args = get_args(type_annotation)
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return (non_none_args[0], True)
    return (type_annotation, False)


def _unwrap_list(type_annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(type_annotation)
    if origin in (list, List):
        args = get_args(type_annotation)
        if args:
            return (args[0], True)
    return (type_annotation, False)


def _msg_name_for_scalar_stream(stream_name: str) -> str:
    return f"{stream_name}Message"


def _determine_proto_type_for_field(
    inner_type: Type[Any],
    seen_models: set[str],
    lines: list[str],
) -> str:
    if inner_type in _SCALAR_MAP:
        return _SCALAR_MAP[inner_type]

    if is_pydantic_model(inner_type):
        model_name = inner_type.__name__
        # Recursively register nested model if not seen before
        if model_name not in seen_models:
            seen_models.add(model_name)
            lines.extend(_generate_pydantic_message(inner_type, seen_models, lines))
        return model_name

    # Fallback to string for unknown types
    return "string"


def _process_pydantic_field(
    field_name: str,
    field_type: Type[Any],
    field_index: int,
    seen_models: set[str],
    lines: list[str],
) -> str:
    inner_type, _ = _unwrap_optional(field_type)
    list_inner_type, is_list = _unwrap_list(inner_type)

    proto_type = _determine_proto_type_for_field(list_inner_type, seen_models, lines)

    if is_list:
        proto_type = f"repeated {proto_type}"

    return f"  {proto_type} {field_name} = {field_index};"


def _generate_pydantic_message(
    type_annotation: Type[Any],
    seen_models: set[str],
    lines: list[str],
) -> list[str]:
    model_name = type_annotation.__name__
    fields = []
    field_index = 1

    for field_name, field_def in type_annotation.model_fields.items():
        field_line = _process_pydantic_field(
            field_name,
            field_def.annotation,
            field_index,
            seen_models,
            lines,
        )
        fields.append(field_line)
        field_index += 1

    lines_result = [f"message {model_name} {{"]
    lines_result.extend(fields)
    lines_result.append("}\n")
    return lines_result


def _generate_scalar_wrapper_message(
    stream_name: str, payload_type: Type[Any]
) -> list[str]:
    wrapper_name = _msg_name_for_scalar_stream(stream_name)
    lines = [
        f"message {wrapper_name} {{",
        f"  {_SCALAR_MAP[payload_type]} value = 1;",
        "}\n",
    ]
    return lines


def _proto_type_name(
    type_annotation: Optional[Type[Any]],
    scalar_wrappers: Dict[str, str],
    stream_name: Optional[str] = None,
) -> str:
    if type_annotation is None:
        return "google.protobuf.Empty"

    inner_type, _ = _unwrap_optional(type_annotation)

    list_inner_type, is_list = _unwrap_list(inner_type)

    if list_inner_type in _SCALAR_MAP:
        if stream_name and stream_name in scalar_wrappers:
            return scalar_wrappers[stream_name]
        return str(_SCALAR_MAP[list_inner_type])

    if is_pydantic_model(list_inner_type):
        return str(list_inner_type.__name__)

    return "google.protobuf.Empty"


def _register_pydantic_model(
    type_annotation: Optional[Type[Any]],
    seen_models: set[str],
    lines: list[str],
) -> None:
    if type_annotation is None:
        return

    inner_type, _ = _unwrap_optional(type_annotation)

    list_inner_type, _ = _unwrap_list(inner_type)

    if is_pydantic_model(list_inner_type):
        model_name = list_inner_type.__name__
        if model_name not in seen_models:
            seen_models.add(model_name)
            lines.extend(
                _generate_pydantic_message(list_inner_type, seen_models, lines)
            )


def _process_stream_payload(
    stream_entry: StreamEntry,
    seen_models: set[str],
    lines: list[str],
    scalar_wrappers: Dict[str, str],
) -> None:
    inner_type, _ = _unwrap_optional(stream_entry.payload_type)
    list_inner_type, _ = _unwrap_list(inner_type)

    if is_pydantic_model(list_inner_type):
        _register_pydantic_model(list_inner_type, seen_models, lines)
    elif list_inner_type in _SCALAR_MAP:
        wrapper_name = _msg_name_for_scalar_stream(stream_entry.name)
        scalar_wrappers[stream_entry.name] = wrapper_name
        lines.extend(
            _generate_scalar_wrapper_message(stream_entry.name, list_inner_type)
        )


def _collect_message_types(
    bundle: RpcBundle,
    lines: list[str],
    seen_models: set[str],
    scalar_wrappers: Dict[str, str],
) -> None:
    for action_entry in bundle.actions:
        _register_pydantic_model(action_entry.input_type, seen_models, lines)
        _register_pydantic_model(action_entry.output_type, seen_models, lines)

    for stream_entry in bundle.streams:
        _process_stream_payload(stream_entry, seen_models, lines, scalar_wrappers)


def _generate_service_rpcs(
    bundle: RpcBundle, lines: list[str], scalar_wrappers: Dict[str, str]
) -> None:
    rpc_prefix = "  rpc"

    for action_entry in bundle.actions:
        input_type = _proto_type_name(action_entry.input_type, scalar_wrappers)
        output_type = _proto_type_name(action_entry.output_type, scalar_wrappers)
        lines.append(
            f"{rpc_prefix} {action_entry.name} ({input_type}) returns ({output_type});"
        )

    for stream_entry in bundle.streams:
        output_type = _proto_type_name(
            stream_entry.payload_type, scalar_wrappers, stream_entry.name
        )
        lines.append(
            f"{rpc_prefix} {stream_entry.name} (google.protobuf.Empty) returns (stream {output_type});"
        )


def generate_proto(app_name: str, *, bundle: Optional[RpcBundle] = None) -> str:
    if bundle is None:
        bundle = collect_bundle()

    lines: list[str] = [HEADER]
    seen_models: set[str] = set()
    scalar_wrappers: Dict[str, str] = {}

    _collect_message_types(bundle, lines, seen_models, scalar_wrappers)

    service_name = sanitize_service_name(app_name)
    lines.append(f"service {service_name}Service {{")
    _generate_service_rpcs(bundle, lines, scalar_wrappers)
    lines.append("}\n")

    return "\n".join(lines)


def sanitize_service_name(name: str) -> str:
    import re

    parts = re.findall(r"[A-Za-z0-9]+", name)
    if not parts:
        return "VentionApp"
    return "".join(part[:1].upper() + part[1:] for part in parts)
