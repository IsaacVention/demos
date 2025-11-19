from __future__ import annotations
import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from sqlmodel import SQLModel   # <-- NEW for SQLModel serialization

from .entries import ActionEntry, StreamEntry
from .errors import error_envelope, to_connect_error

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/connect+json"


# ============================================================
# Helper: Convert Python → JSON-safe (supports SQLModel, Pydantic, lists, dicts)
# ============================================================

def _to_serializable(obj: Any) -> Any:
    """Normalize any Python object into JSON-safe data with aliasing."""
    # SQLModel (ORM objects)
    if isinstance(obj, SQLModel):
        return obj.model_dump(by_alias=True)

    # Pydantic models
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)

    # list or tuple
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(x) for x in obj]

    # dict
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}

    # passthrough primitive types
    return obj


# ============================================================
# Connect JSON framing for streams
# ============================================================

def _frame(payload: Dict[str, Any], *, trailer: bool = False) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    flag = 0x80 if trailer else 0x00
    header = bytes([flag]) + len(body).to_bytes(4, byteorder="big", signed=False)
    return header + body


# ============================================================
# Subscriber
# ============================================================

@dataclass(eq=False, unsafe_hash=True)
class _Subscriber:
    queue: asyncio.Queue[Any]
    joined_at: float = field(default_factory=lambda: time.time())
    last_send_at: float = field(default_factory=lambda: time.time())


# ============================================================
# Stream Manager — fan-out with policies
# ============================================================

class StreamManager:
    def __init__(self) -> None:
        self._topics: Dict[str, Dict[str, Any]] = {}

    def ensure_topic(self, entry: StreamEntry) -> None:
        if entry.name in self._topics:
            return

        publish_queue: asyncio.Queue[Any] = asyncio.Queue()
        subscribers: set[_Subscriber] = set()
        topic = {
            "entry": entry,
            "publish_queue": publish_queue,
            "subscribers": subscribers,
            "last_value": None,
            "task": None,
        }
        self._topics[entry.name] = topic

        try:
            loop = asyncio.get_running_loop()
            topic["task"] = loop.create_task(self._distributor(entry.name))
        except RuntimeError:
            pass

    def start_distributor_if_needed(self, stream_name: str) -> None:
        topic = self._topics[stream_name]
        if topic["task"] is None or topic["task"].done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            topic["task"] = loop.create_task(self._distributor(stream_name))

    def add_stream(self, entry: StreamEntry) -> None:
        self.ensure_topic(entry)

    def publish(self, stream_name: str, item: Any) -> None:
        topic = self._topics.get(stream_name)
        if topic is None:
            raise KeyError(f"Unknown stream: {stream_name}")
        self.start_distributor_if_needed(stream_name)
        topic["publish_queue"].put_nowait(item)

    def subscribe(self, stream_name: str) -> _Subscriber:
        topic = self._topics[stream_name]
        entry: StreamEntry = topic["entry"]

        subscriber_queue: asyncio.Queue[Any] = asyncio.Queue(
            maxsize=entry.queue_maxsize
        )
        subscriber = _Subscriber(queue=subscriber_queue)
        topic["subscribers"].add(subscriber)
        self.start_distributor_if_needed(stream_name)

        if entry.replay and topic["last_value"] is not None:
            try:
                subscriber_queue.put_nowait(topic["last_value"])
            except asyncio.QueueFull:
                _ = subscriber_queue.get_nowait()
                subscriber_queue.put_nowait(topic["last_value"])
        return subscriber

    def unsubscribe(self, stream_name: str, subscriber: _Subscriber) -> None:
        topic = self._topics.get(stream_name)
        if topic:
            topic["subscribers"].discard(subscriber)

    async def _distributor(self, stream_name: str) -> None:
        topic = self._topics[stream_name]
        publish_queue: asyncio.Queue[Any] = topic["publish_queue"]
        subscribers: set[_Subscriber] = topic["subscribers"]

        while True:
            item = await publish_queue.get()
            topic["last_value"] = item
            dead: List[_Subscriber] = []
            entry: StreamEntry = topic["entry"]

            for sub in list(subscribers):
                try:
                    if entry.policy == "fifo":
                        await sub.queue.put(item)
                    else:
                        sub.queue.put_nowait(item)
                except asyncio.QueueFull:
                    try:
                        _ = sub.queue.get_nowait()
                    except Exception:
                        pass
                    try:
                        sub.queue.put_nowait(item)
                    except Exception:
                        dead.append(sub)

            for d in dead:
                subscribers.discard(d)


# ============================================================
# ConnectRouter — unary + streaming RPCs
# ============================================================

class ConnectRouter:
    def __init__(self) -> None:
        self.router = APIRouter()
        self._unaries: Dict[str, ActionEntry] = {}
        self._streams: Dict[str, StreamEntry] = {}
        self.manager = StreamManager()

    # ----------------------------
    # Unary RPC
    # ----------------------------

    def add_unary(self, entry: ActionEntry, service_fqn: str) -> None:
        self._unaries[entry.name] = entry
        path = f"/{service_fqn}/{entry.name}"

        @self.router.post(path)
        async def _handler(request: Request) -> JSONResponse:

            try:
                request_body = await request.json()
            except Exception:
                request_body = {}

            try:
                if entry.input_type is None:
                    result = await _maybe_await(entry.func())
                else:
                    input_type = entry.input_type

                    # VALIDATION
                    validated_arg = input_type.model_validate(request_body)

                    # Call function
                    result = await _maybe_await(entry.func(validated_arg))

                # DUMP RESULT
                if hasattr(result, "model_dump"):
                    dumped = result.model_dump(by_alias=True)
                    return JSONResponse(dumped or {})

                return JSONResponse(result or {})

            except Exception as exc:
                return JSONResponse(error_envelope(exc))


    # ----------------------------
    # Streaming RPC
    # ----------------------------

    def add_stream(self, entry: StreamEntry, service_fqn: str) -> None:
        self._streams[entry.name] = entry
        self.manager.add_stream(entry)

        path = f"/{service_fqn}/{entry.name}"

        async def _stream_iter(subscriber: _Subscriber):
            try:
                while True:
                    item = await subscriber.queue.get()
                    payload = _serialize_stream_item(item)
                    yield _frame(payload)
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                trailer = error_envelope(to_connect_error(exc))
                yield _frame(trailer, trailer=True)
            finally:
                self.manager.unsubscribe(entry.name, subscriber)

        @self.router.post(path)
        async def _handler(_: Request) -> StreamingResponse:
            self.manager.start_distributor_if_needed(entry.name)
            subscriber = self.manager.subscribe(entry.name)
            logger.debug(f"Stream subscribed: {entry.name}")
            return StreamingResponse(
                _stream_iter(subscriber),
                media_type=CONTENT_TYPE,
                headers={"Transfer-Encoding": "chunked"},
            )

    # ----------------------------
    # Publisher API
    # ----------------------------

    def publish(self, stream_name: str, item: Any) -> None:
        if stream_name not in self.manager._topics:
            entry = self._streams.get(stream_name)
            if not entry:
                raise KeyError(f"Unknown stream: {stream_name}")
            self.manager.add_stream(entry)
        self.manager.publish(stream_name, item)


# ============================================================
# Stream Serialization
# ============================================================

def _serialize_stream_item(item: Any) -> Dict[str, Any]:
    return _to_serializable(item)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value
