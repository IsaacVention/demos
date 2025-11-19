from __future__ import annotations
from typing import Any, List

from fastapi import FastAPI

from .connect_router import ConnectRouter
from .decorators import collect_bundle, set_global_app
from .codegen import generate_proto, sanitize_service_name
from .entries import RpcBundle
from .registry import RpcRegistry


class VentionApp(FastAPI):
    """
    FastAPI app that registers Connect-style RPCs and streams from decorators.
    Can be extended with external RpcBundles (state-machine, storage, etc.).

    Responsibilities:
    - Collect bundles (decorators + plugins)
    - Hand them to RpcRegistry
    - Use the unified, normalized bundle to:
        * wire ConnectRouter
        * optionally generate .proto
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

        # External bundles (from vention-storage, vention-state-machine, etc.)
        self._extra_bundles: List[RpcBundle] = []

        # Registry that owns the canonical bundle + aliasing
        self._registry = RpcRegistry(service_name=self.service_name)

    def register_rpc_plugin(self, bundle: RpcBundle) -> None:
        """Add RPCs/streams provided by external libraries.

        Must be called before finalize().

        Args:
            bundle: RPC bundle containing actions and streams to register
        """
        self._extra_bundles.append(bundle)

    def finalize(self) -> None:
        """Finalize the app by registering all RPCs and streams.

        Steps:
        - Collect decorator-registered RPCs
        - Merge in external bundles
        - Use RpcRegistry to:
            * apply aliases to all Pydantic models
            * provide a unified RpcBundle
        - Wire actions/streams into ConnectRouter
        - Mount router at /rpc
        - Optionally generate .proto
        - Expose global app for stream publishers
        """
        # 1) Collect local bundle from decorators
        base_bundle = collect_bundle()

        # 2) Register bundles with the registry
        self._registry.add_bundle(base_bundle)
        for extra_bundle in self._extra_bundles:
            self._registry.add_bundle(extra_bundle)

        # 3) Get the unified, normalized bundle (aliases applied)
        unified_bundle = self._registry.get_unified_bundle()

        # 4) Wire up ConnectRouter
        service_fqn = f"vention.app.v1.{self.service_name}Service"
        self.connect_router = ConnectRouter() 

        for action_entry in unified_bundle.actions:
            self.connect_router.add_unary(action_entry, service_fqn)

        for stream_entry in unified_bundle.streams:
            self.connect_router.add_stream(stream_entry, service_fqn)

        self.include_router(self.connect_router.router, prefix="/rpc")

        # 5) Optionally generate proto from the same unified bundle
        if self.emit_proto:
            proto_text = generate_proto(self.service_name, bundle=unified_bundle)

            import os

            os.makedirs(os.path.dirname(self.proto_path), exist_ok=True)
            with open(self.proto_path, "w", encoding="utf-8") as f:
                f.write(proto_text)

        # 6) Make the app visible to @stream publisher wrappers
        set_global_app(self)

    @property
    def service_name(self) -> str:
        """Get the sanitized service name derived from the app name.

        Returns:
            Sanitized service name suitable for proto generation
        """
        return sanitize_service_name(self.name)