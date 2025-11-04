# codegen.py

from __future__ import annotations
from typing import Any, Dict, Optional, Type

from .decorators import collect_bundle
from .typing_utils import is_pydantic_model
from .entries import RpcBundle

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


def _msg_name_for_scalar_stream(stream_name: str) -> str:
    return f"{stream_name}Message"


def _model_name(tp: Type[Any]) -> Optional[str]:
    if is_pydantic_model(tp):
        return tp.__name__
    return None


def generate_proto(app_name: str, *, bundle: Optional[RpcBundle] = None) -> str:
    # 👇 this was the problem: we always called collect_bundle()
    # now we only do it if caller didn't give us a bundle
    if bundle is None:
        bundle = collect_bundle()

    uses_empty = False
    lines: list[str] = [HEADER]

    # --- message types (pydantic models + scalar wrappers) ---
    seen_models: set[str] = set()
    scalar_wrappers: Dict[str, str] = {}

    def touch_model(tp: Optional[Type[Any]]) -> None:
        """
        Register a message for a given Python type.
        If we can't map it (e.g. dict), we just mark that we need Empty.
        """
        nonlocal uses_empty
        if tp is None:
            uses_empty = True
            return
        if is_pydantic_model(tp):
            name = tp.__name__
            if name in seen_models:
                return
            seen_models.add(name)
            fields = []
            idx = 1
            for fname, fdef in tp.model_fields.items():  # type: ignore[attr-defined]
                t = fdef.annotation
                if t in _SCALAR_MAP:
                    fields.append(f"  {_SCALAR_MAP[t]} {fname} = {idx};")
                else:
                    # fallback: untyped / complex → string
                    fields.append(f"  string {fname} = {idx};")
                idx += 1
            lines.append(f"message {name} {{")
            lines.extend(fields)
            lines.append("}\n")
        elif tp in _SCALAR_MAP:
            # Nothing to declare; primitive
            pass
        else:
            # dict, list, whatever → we’ll just use Empty
            uses_empty = True

    # collect models from actions
    for a in bundle.actions:
        touch_model(a.input_type)
        touch_model(a.output_type)

    # collect models from streams
    for s in bundle.streams:
        uses_empty = True  # streams always take Empty
        if is_pydantic_model(s.payload_type):
            touch_model(s.payload_type)
        elif s.payload_type in _SCALAR_MAP:
            # make wrapper for scalar payload
            wn = _msg_name_for_scalar_stream(s.name)
            scalar_wrappers[s.name] = wn
            lines.append(f"message {wn} {{")
            lines.append(f"  {_SCALAR_MAP[s.payload_type]} value = 1;")
            lines.append("}\n")
        else:
            # dict / unknown → just stream Empty
            uses_empty = True

    # --- service ---
    service = f"service {sanitize_service_name(app_name)}Service {{"
    lines.append(service)

    svc_prefix = "  rpc"

    # actions
    for a in bundle.actions:
        if a.input_type is None:
            in_t = "google.protobuf.Empty"
        elif a.input_type in _SCALAR_MAP:
            in_t = _SCALAR_MAP[a.input_type]
        elif is_pydantic_model(a.input_type):
            in_t = a.input_type.__name__
        else:
            in_t = "google.protobuf.Empty"

        if a.output_type is None:
            out_t = "google.protobuf.Empty"
        elif a.output_type in _SCALAR_MAP:
            out_t = _SCALAR_MAP[a.output_type]
        elif is_pydantic_model(a.output_type):
            out_t = a.output_type.__name__
        else:
            out_t = "google.protobuf.Empty"

        lines.append(f"{svc_prefix} {a.name} ({in_t}) returns ({out_t});")

    # streams
    for s in bundle.streams:
        if is_pydantic_model(s.payload_type):
            out_t = s.payload_type.__name__
        elif s.payload_type in _SCALAR_MAP:
            out_t = scalar_wrappers[s.name]
        else:
            out_t = "google.protobuf.Empty"
        lines.append(
            f"{svc_prefix} {s.name} (google.protobuf.Empty) returns (stream {out_t});"
        )

    lines.append("}\n")

    return "\n".join(lines)


def sanitize_service_name(name: str) -> str:
    # Letters/digits, capitalize words, drop invalid chars
    import re

    parts = re.findall(r"[A-Za-z0-9]+", name)
    if not parts:
        return "VentionApp"
    return "".join(p[:1].upper() + p[1:] for p in parts)
