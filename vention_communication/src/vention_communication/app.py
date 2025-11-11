from __future__ import annotations
from typing import Any, List

from fastapi import FastAPI

from .connect_router import ConnectRouter
from .decorators import collect_bundle, set_global_app
from .codegen import generate_proto, sanitize_service_name
from .entries import RpcBundle


class VentionApp(FastAPI):
    """
    FastAPI app that registers Connect-style RPCs and streams from decorators.
    Can be extended with external RpcBundles (state-machine, storage, etc.).
    """

    def __init__(
        self,
        name: str = "VentionApp",
        *,
        emit_proto: bool = False,
        proto_path: str = "proto/app.proto",
        **kwargs: Any,
    ) -> None:
        """Initialize the VentionApp.

        Args:
            name: Application name, also used as service_name for proto generation
            emit_proto: Whether to emit protocol buffer definitions
            proto_path: Path where proto definitions will be written
            **kwargs: Additional arguments passed to FastAPI
        """
        super().__init__(**kwargs)
        self.name = name
        self.emit_proto = emit_proto
        self.proto_path = proto_path
        self.connect_router = ConnectRouter()
        self._extra_bundles: List[RpcBundle] = []

    def register_rpc_plugin(self, bundle: RpcBundle) -> None:
        """Add RPCs/streams provided by external libraries.

        Must be called before finalize().

        Args:
            bundle: RPC bundle containing actions and streams to register
        """
        self._extra_bundles.append(bundle)

    def finalize(self) -> None:
        """Finalize the app by registering all RPCs and streams.

        Collects decorator-registered RPCs, merges external bundles,
        registers them with the Connect router, optionally emits proto
        definitions, and makes the app available to stream publishers.
        """
        bundle = collect_bundle()
        for extra_bundle in self._extra_bundles:
            bundle.extend(extra_bundle)

        service_fully_qualified_name = f"vention.app.v1.{self.service_name}Service"

        for action_entry in bundle.actions:
            self.connect_router.add_unary(action_entry, service_fully_qualified_name)
        for stream_entry in bundle.streams:
            self.connect_router.add_stream(stream_entry, service_fully_qualified_name)

        self.include_router(self.connect_router.router, prefix="/rpc")

        if self.emit_proto:
            proto = generate_proto(self.service_name, bundle=bundle)
            import os

            os.makedirs(os.path.dirname(self.proto_path), exist_ok=True)
            with open(self.proto_path, "w", encoding="utf-8") as proto_file:
                proto_file.write(proto)

        set_global_app(self)

    @property
    def service_name(self) -> str:
        """Get the sanitized service name derived from the app name.

        Returns:
            Sanitized service name suitable for proto generation
        """
        return sanitize_service_name(self.name)
