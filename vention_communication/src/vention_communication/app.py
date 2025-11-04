# app.py

from __future__ import annotations
from typing import List

from fastapi import FastAPI

from .connect_router import ConnectRouter
from .decorators import collect_bundle, set_global_app
from .codegen import generate_proto
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
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.name = name
        self.emit_proto = emit_proto
        self.proto_path = proto_path
        self.connect_router = ConnectRouter()
        # external bundles accumulated before finalize()
        self._extra_bundles: List[RpcBundle] = []

    def extend_bundle(self, bundle: RpcBundle) -> None:
        """
        Add RPCs/streams provided by external libraries BEFORE finalize().
        """
        self._extra_bundles.append(bundle)

    def finalize(self) -> None:
        # 1) Collect declared RPCs/streams from decorators
        bundle = collect_bundle()

        # 2) Merge external bundles
        for extra_bundle in self._extra_bundles:
            print("Extending bundle")
            print(extra_bundle)
            bundle.extend(extra_bundle)

        service_fqn = f"vention.app.v1.{self.service_name}Service"

        # 3) Register on our connect router
        for a in bundle.actions:
            self.connect_router.add_unary(a, service_fqn)
        for s in bundle.streams:
            self.connect_router.add_stream(s, service_fqn)

        # 4) Mount router
        self.include_router(self.connect_router.router, prefix="/rpc")

        # 5) Emit proto from the MERGED bundle (this was the missing piece)
        if self.emit_proto:
            proto = generate_proto(self.service_name, bundle=bundle)
            import os

            os.makedirs(os.path.dirname(self.proto_path), exist_ok=True)
            with open(self.proto_path, "w", encoding="utf-8") as f:
                f.write(proto)

        # 6) Make available to publisher wrappers
        set_global_app(self)

    # Service name derived from app name
    @property
    def service_name(self) -> str:
        from .codegen import sanitize_service_name

        return sanitize_service_name(self.name)
