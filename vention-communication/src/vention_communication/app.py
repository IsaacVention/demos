from fastapi import FastAPI
from .connect_router import ConnectRouter
from .entries import RpcBundle, ActionEntry, StreamEntry
from .decorators import _get_registered_actions, _get_registered_streams

class VentionApp(FastAPI):
    """
    Wrapper around FastAPI providing decorator-based RPC registration
    and automatic proto emission.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        _GLOBAL_APP = None
        self.actions: dict[str, ActionEntry] = {}
        self.streams: dict[str, StreamEntry] = {}
        self.connect_router = ConnectRouter()
        self._finalized = False

    def extend(self, bundle: RpcBundle):
        self.actions.update(bundle.actions)
        self.streams.update(bundle.streams)

    def finalize(self, *, emit_proto=True, out_dir="proto/"):
        global _GLOBAL_APP
        _GLOBAL_APP = self
        if self._finalized:
            return
        self.actions = _get_registered_actions()
        self.streams = _get_registered_streams()
        
        # Register ConnectRPC routes
        for name, entry in self.actions.items():
            self.connect_router.add_unary(
                name, entry.fn, entry.input_type, entry.output_type
            )
        for name, entry in self.streams.items():
            self.connect_router.add_stream(name, entry.handler, entry.payload)
        self.include_router(self.connect_router, prefix="/rpc")

        if emit_proto:
            from .codegen import emit_proto
            emit_proto(self.actions, self.streams, out_dir)
        self._finalized = True
