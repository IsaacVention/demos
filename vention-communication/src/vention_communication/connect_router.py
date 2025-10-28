# src/vention_communication/connect_router.py
"""
Custom JSON-based Connect-like router for unary and streaming RPCs.

Stage 1 runtime: JSON over HTTP/1.1
Compatible with ConnectRPC clients (connect-es) using `useBinaryFormat: false`.
"""

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, Type
import struct

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel


class ConnectRouter(APIRouter):
    """
    Custom ASGI router that registers and serves unary and streaming RPCs
    using JSON serialization for maximum browser compatibility.

    The actual Connect wire framing (envelopes/trailers) can be added later
    for full ConnectRPC compliance.
    """

    def __init__(self):
        super().__init__()
        self.unary_handlers: Dict[str, Callable[[Any], Awaitable[Any]]] = {}
        self.stream_handlers: Dict[str, Callable[..., Awaitable[Any]]] = {}

    # -------------------------------------------------------
    # UNARY CALLS
    # -------------------------------------------------------
    def add_unary(
        self,
        name: str,
        fn: Callable[..., Awaitable[Any]],
        input_type: Type[BaseModel],
        output_type: Type[BaseModel],
    ):
        rpc_name = name[0].upper() + name[1:]
        route_path = f"/vention.app.v1.VentionAppService/{rpc_name}"
        self.unary_handlers[name] = fn

        @self.post(route_path)
        async def unary_endpoint(request: Request):
            try:
                payload = await request.json()
                model = input_type(**payload) if input_type and payload else None
                result = await fn(model) if model else await fn()
                # if Pydantic model returned, convert to dict
                if isinstance(result, BaseModel):
                    result = result.model_dump()
                return JSONResponse(result)
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

    # -------------------------------------------------------
    # SERVER STREAMS
    # -------------------------------------------------------
    def add_stream(
        self,
        name: str,
        handler: Callable[..., Awaitable[Any]],
        payload_type: Type[Any],
    ):
        rpc_name = name[0].upper() + name[1:]
        route_path = f"/vention.app.v1.VentionAppService/{rpc_name}"

        @self.post(route_path)
        async def stream_endpoint(request: Request):
            """
            Each subscriber opens a new HTTP connection that remains open.
            The handler publishes messages to an asyncio.Queue shared by this client.
            """
            q: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_event_loop()

            async def event_generator():
                while True:
                    msg = await q.get()
                    if isinstance(msg, BaseModel):
                        msg = msg.model_dump()
                    frame = {"value": msg} if not isinstance(msg, (dict, list)) else msg

                    # Encode as Connect envelope
                    payload = json.dumps(frame).encode("utf-8")
                    # 1 byte flag (0 for data), 4 bytes length prefix (big-endian)
                    header = b"\x00" + struct.pack(">I", len(payload))
                    yield header + payload



            # Spawn background task to populate queue
            async def run_handler():
                try:
                    while True:
                        data = await handler()
                        await q.put(data)
                        await asyncio.sleep(1)  # throttle demo streams
                except asyncio.CancelledError:
                    pass

            task = loop.create_task(run_handler())

            # Ensure cleanup on disconnect
            async def on_disconnect():
                task.cancel()

            request.scope["on_disconnect"] = on_disconnect
            return StreamingResponse(
                event_generator(),
                media_type="application/connect+json",
                headers={
                    "transfer-encoding": "chunked",
                    "x-content-type-options": "nosniff",
                },
            )


