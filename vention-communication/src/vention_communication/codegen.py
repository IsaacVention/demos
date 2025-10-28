# src/vention_communication/codegen.py
"""
Code-generator for .proto schema from registered actions and streams.

✅ Supports
    - Pydantic models
    - Scalar types (str, int, float, bool, bytes)
    - Empty requests/responses (→ google.protobuf.Empty)
    - Server streams (including scalar payloads)

⚠️ Not yet supported
    - List, Optional, Union, nested models, enums
"""

from pathlib import Path
from typing import Any
from pydantic import BaseModel

from .entries import ActionEntry, StreamEntry
from .utils.typing_utils import Empty, is_pydantic_model

# --------------------------------------------------------------------------- #
# Type mapping
# --------------------------------------------------------------------------- #

_SCALAR_MAP = {
    str: "string",
    int: "int64",
    float: "double",
    bool: "bool",
    bytes: "bytes",
}

_EMPTY_IMPORT = 'import "google/protobuf/empty.proto";'


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _proto_type_of(py_type: type) -> str:
    """Return the proto type name for a given Python type."""
    if py_type is Empty:
        return "google.protobuf.Empty"
    if py_type in _SCALAR_MAP:
        return _SCALAR_MAP[py_type]
    if is_pydantic_model(py_type):
        return py_type.__name__
    raise ValueError(f"Unsupported type for proto generation: {py_type!r}")


def _emit_message_for_model(model: type[BaseModel]) -> list[str]:
    """Emit a `message` definition for a Pydantic model."""
    lines: list[str] = [f"message {model.__name__} {{"]
    num = 1
    for name, field in model.model_fields.items():
        field_type = field.annotation
        try:
            proto_type = _proto_type_of(field_type)
        except ValueError:
            raise ValueError(
                f"Field {model.__name__}.{name} has unsupported type {field_type!r}"
            )
        lines.append(f"  {proto_type} {name} = {num};")
        num += 1
    lines.append("}")
    return lines


def _uses_empty(actions: dict, streams: dict) -> bool:
    for entry in actions.values():
        if entry.input_type is Empty or entry.output_type is Empty:
            return True
    for entry in streams.values():
        # streams always have Empty input
        return True
    return False


# --------------------------------------------------------------------------- #
# Main emitter
# --------------------------------------------------------------------------- #


def emit_proto(
    actions: dict[str, ActionEntry],
    streams: dict[str, StreamEntry],
    out_dir: str,
    package: str = "vention.app.v1",
) -> None:
    """
    Generate a .proto file containing:
      - syntax = "proto3"
      - package <package>
      - Imports if needed
      - message definitions (models + scalar wrappers)
      - service definition with all RPC methods
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    file_path = out_path / "app.proto"

    # ------------------------------------------------------------------ #
    # Collect message models
    # ------------------------------------------------------------------ #
    message_models: set[type] = set()
    for entry in actions.values():
        if entry.input_type is not Empty and is_pydantic_model(entry.input_type):
            message_models.add(entry.input_type)
        if entry.output_type is not Empty and is_pydantic_model(entry.output_type):
            message_models.add(entry.output_type)
    for entry in streams.values():
        if entry.payload is not Empty and is_pydantic_model(entry.payload):
            message_models.add(entry.payload)

    # ------------------------------------------------------------------ #
    # Start building proto file
    # ------------------------------------------------------------------ #
    lines: list[str] = [
        'syntax = "proto3";',
        f"package {package};",
        "",
    ]

    # Include Empty import if used
    uses_empty = _uses_empty(actions, streams)

    if uses_empty:
        lines.append(_EMPTY_IMPORT)
        lines.append("")

    # ------------------------------------------------------------------ #
    # Emit Pydantic model messages
    # ------------------------------------------------------------------ #
    for model in sorted(message_models, key=lambda m: m.__name__):
        lines.extend(_emit_message_for_model(model))
        lines.append("")

    # ------------------------------------------------------------------ #
    # Prepare scalar wrapper messages + service lines
    # ------------------------------------------------------------------ #
    scalar_wrappers: list[tuple[str, str]] = []
    service_lines: list[str] = []

    # ---- Actions ----
    for name, entry in actions.items():
        rpc_name = name[0].upper() + name[1:]
        input_name = (
            "google.protobuf.Empty"
            if entry.input_type is Empty
            else entry.input_type.__name__
        )
        output_name = (
            "google.protobuf.Empty"
            if entry.output_type is Empty
            else entry.output_type.__name__
        )
        service_lines.append(f"  rpc {rpc_name}({input_name}) returns ({output_name});")

    # ---- Streams ----
    for name, entry in streams.items():
        rpc_name = name[0].upper() + name[1:]
        payload_type = entry.payload

        if payload_type is Empty:
            payload_name = "google.protobuf.Empty"
        elif payload_type in _SCALAR_MAP:
            msg_name = f"{rpc_name}Message"
            scalar_wrappers.append((msg_name, _SCALAR_MAP[payload_type]))
            payload_name = msg_name
        elif is_pydantic_model(payload_type):
            payload_name = payload_type.__name__
        else:
            raise ValueError(
                f"Unsupported stream payload type for {rpc_name}: {payload_type!r}"
            )

        service_lines.append(
            f"  rpc {rpc_name}(google.protobuf.Empty) returns (stream {payload_name});"
        )

    # ------------------------------------------------------------------ #
    # Emit scalar wrapper messages before the service
    # ------------------------------------------------------------------ #
    for msg_name, scalar_type in scalar_wrappers:
        lines.append(f"message {msg_name} {{")
        lines.append(f"  {scalar_type} value = 1;")
        lines.append("}")
        lines.append("")

    # ------------------------------------------------------------------ #
    # Emit service definition
    # ------------------------------------------------------------------ #
    lines.append("service VentionAppService {")
    lines.extend(service_lines)
    lines.append("}")

    # ------------------------------------------------------------------ #
    # Write file
    # ------------------------------------------------------------------ #
    file_path.write_text("\n".join(lines) + "\n")
    print(f"[vention-communication] emitted .proto → {file_path}")
