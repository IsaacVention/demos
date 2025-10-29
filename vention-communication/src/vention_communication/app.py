# app.py

from __future__ import annotations

from fastapi import FastAPI

from .connect_router import ConnectRouter
from .decorators import collect_bundle, set_global_app
from .codegen import generate_proto


class VentionApp(FastAPI):
    """
    FastAPI app that registers Connect-style RPCs and streams from decorators.
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

    def finalize(self) -> None:
        # Collect declared RPCs/streams
        bundle = collect_bundle()
        service_fqn = f"vention.app.v1.{self.service_name}Service"

        # Register
        for a in bundle.actions:
            self.connect_router.add_unary(a, service_fqn)
        for s in bundle.streams:
            # create topic (async init happens on first subscribe/post)
            self.connect_router.add_stream(s, service_fqn)

        # Mount router
        self.include_router(self.connect_router.router, prefix="/rpc")

        # Emit proto if asked
        if self.emit_proto:
            proto = generate_proto(self.service_name)
            import os

            os.makedirs(os.path.dirname(self.proto_path), exist_ok=True)
            with open(self.proto_path, "w", encoding="utf-8") as f:
                f.write(proto)

        # Make available to publisher wrappers
        set_global_app(self)

    # Service name derived from app name
    @property
    def service_name(self) -> str:
        from .codegen import sanitize_service_name

        return sanitize_service_name(self.name)
