from __future__ import annotations
import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .entries import ActionEntry, StreamEntry
from .errors import error_envelope, to_connect_error

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/connect+json"


# ---------- Frame encoding ----------


def _frame(payload: Dict[str, Any], *, trailer: bool = False) -> bytes:
    """Connect JSON frame: 1 byte flags + 4 bytes len (big-endian) + JSON bytes."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    flag = 0x80 if trailer else 0x00
    header = bytes([flag]) + len(body).to_bytes(4, byteorder="big", signed=False)
    return header + body


# ---------- Subscriber ----------


@dataclass(eq=False, unsafe_hash=True)
class _Subscriber:
    queue: asyncio.Queue
    joined_at: float = field(default_factory=lambda: time.time())
    last_send_at: float = field(default_factory=lambda: time.time())


# ---------- StreamManager ----------


class StreamManager:
    """Topic-oriented fan-out with a distributor task per stream (latest-wins)."""

    def __init__(self) -> None:
        # name -> dict(entry, publish_queue, subscribers, last_value, task)
        self._topics: Dict[str, Dict[str, Any]] = {}

    # --- topic lifecycle ---

    def ensure_topic(self, entry: StreamEntry) -> None:
        """Create a topic if it doesn't exist (synchronous, safe before loop)."""
        if entry.name in self._topics:
            return

        publish_queue: asyncio.Queue = asyncio.Queue()
        subs: set[_Subscriber] = set()
        topic = {
            "entry": entry,
            "publish_queue": publish_queue,
            "subscribers": subs,
            "last_value": None,
            "task": None,
        }
        self._topics[entry.name] = topic

        # If an event loop is running, start distributor immediately
        try:
            loop = asyncio.get_running_loop()
            topic["task"] = loop.create_task(self._distributor(entry.name))
        except RuntimeError:
            # Will be started lazily later
            pass

    def start_distributor_if_needed(self, name: str) -> None:
        topic = self._topics[name]
        if topic["task"] is None or topic["task"].done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            topic["task"] = loop.create_task(self._distributor(name))

    def add_stream(self, entry: StreamEntry) -> None:
        self.ensure_topic(entry)

    # --- publish/subscribe ---

    def publish(self, stream_name: str, item: Any) -> None:
        topic = self._topics.get(stream_name)
        if topic is None:
            raise KeyError(f"Unknown stream: {stream_name}")
        self.start_distributor_if_needed(stream_name)
        topic["publish_queue"].put_nowait(item)

    def subscribe(self, stream_name: str) -> _Subscriber:
        topic = self._topics[stream_name]
        entry: StreamEntry = topic["entry"]
        q: asyncio.Queue = asyncio.Queue(maxsize=entry.queue_maxsize)
        sub = _Subscriber(queue=q)
        topic["subscribers"].add(sub)
        self.start_distributor_if_needed(stream_name)
        # Optional replay
        if entry.replay and topic["last_value"] is not None:
            try:
                q.put_nowait(topic["last_value"])
            except asyncio.QueueFull:
                _ = q.get_nowait()
                q.put_nowait(topic["last_value"])
        return sub

    def unsubscribe(self, stream_name: str, sub: _Subscriber) -> None:
        topic = self._topics.get(stream_name)
        if topic:
            topic["subscribers"].discard(sub)

    # --- distributor (latest-wins per subscriber) ---

    async def _distributor(self, stream_name: str) -> None:
        topic = self._topics[stream_name]
        publish_queue: asyncio.Queue = topic["publish_queue"]
        subs: set[_Subscriber] = topic["subscribers"]

        while True:
            item = await publish_queue.get()
            topic["last_value"] = item
            dead: list[_Subscriber] = []
            entry: StreamEntry = topic["entry"]

            for sub in list(subs):
                try:
                    if entry.policy == "fifo":
                        # Wait until space is free; preserve order
                        await sub.queue.put(item)
                    else:
                        # latest-wins: drop oldest and push newest
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
                subs.discard(d)


# ---------- ConnectRouter ----------


class ConnectRouter:
    def __init__(self) -> None:
        self.router = APIRouter()
        self._unaries: Dict[str, ActionEntry] = {}
        self._streams: Dict[str, StreamEntry] = {}
        self.manager = StreamManager()

    # --- Registration (unary) ---

    def add_unary(self, entry: ActionEntry, service_fqn: str) -> None:
        self._unaries[entry.name] = entry
        path = f"/{service_fqn}/{entry.name}"

        @self.router.post(path)
        async def _handler(req: Request) -> JSONResponse:
            try:
                body = await req.json()
            except Exception:
                body = {}

            try:
                if entry.input_type is None:
                    result = await _maybe_await(entry.func())
                else:
                    arg_type = entry.input_type
                    if hasattr(arg_type, "model_validate"):
                        arg = arg_type.model_validate(body)
                    else:
                        arg = body
                    result = await _maybe_await(entry.func(arg))

                if hasattr(result, "model_dump"):
                    result = result.model_dump()
                return JSONResponse(result or {})
            except Exception as e:
                return JSONResponse(error_envelope(e))

    # --- Registration (stream) ---

    def add_stream(self, entry: StreamEntry, service_fqn: str) -> None:
        # Eagerly create topic so early publishers work
        self._streams[entry.name] = entry
        self.manager.add_stream(entry)

        path = f"/{service_fqn}/{entry.name}"

        async def _stream_iter(sub: _Subscriber) -> Any:
            """Async generator yielding Connect frames for each stream item."""
            try:
                while True:
                    item = await sub.queue.get()
                    payload = _serialize_stream_item(item)
                    yield _frame(payload)
                    await asyncio.sleep(0)  # allow flush per frame
            except asyncio.CancelledError:
                raise
            except Exception as e:
                trailer = error_envelope(to_connect_error(e))
                yield _frame(trailer, trailer=True)
            finally:
                self.manager.unsubscribe(entry.name, sub)

        @self.router.post(path)
        async def _handler(_: Request) -> StreamingResponse:
            self.manager.start_distributor_if_needed(entry.name)
            sub = self.manager.subscribe(entry.name)
            logger.debug(f"Stream subscribed: {entry.name}")
            return StreamingResponse(
                _stream_iter(sub),
                media_type=CONTENT_TYPE,
                headers={"Transfer-Encoding": "chunked"},
            )

    # --- Utilities ---

    def publish(self, name: str, item: Any) -> None:
        if name not in self.manager._topics:
            entry = self._streams.get(name)
            if not entry:
                raise KeyError(f"Unknown stream: {name}")
            self.manager.add_stream(entry)
        self.manager.publish(name, item)


# ---------- Helpers ----------


def _serialize_stream_item(item: Any) -> Dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if isinstance(item, (dict, list)):
        return item  # type: ignore[return-value]
    return {"value": item}


async def _maybe_await(v: Any) -> Any:
    if asyncio.iscoroutine(v) or isinstance(v, asyncio.Future):
        return await v
    return v
