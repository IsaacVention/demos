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


def _frame(payload: Dict[str, Any], *, trailer: bool = False) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    flag = 0x80 if trailer else 0x00
    header = bytes([flag]) + len(body).to_bytes(4, byteorder="big", signed=False)
    return header + body


# ---------- Subscriber ----------


@dataclass(eq=False, unsafe_hash=True)
class _Subscriber:
    queue: asyncio.Queue[Any]
    joined_at: float = field(default_factory=lambda: time.time())
    last_send_at: float = field(default_factory=lambda: time.time())


class StreamManager:
    """Topic-oriented fan-out with a distributor task per stream.

    Supports configurable delivery policies: "latest" (drops old items when queue is full)
    or "fifo" (waits for space to ensure all items are delivered).
    """

    def __init__(self) -> None:
        self._topics: Dict[str, Dict[str, Any]] = {}

    def ensure_topic(self, entry: StreamEntry) -> None:
        """Create a topic if it doesn't exist (synchronous, safe before loop)."""
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

        # If an event loop is running, start distributor immediately
        try:
            loop = asyncio.get_running_loop()
            topic["task"] = loop.create_task(self._distributor(entry.name))
        except RuntimeError:
            pass

    def start_distributor_if_needed(self, stream_name: str) -> None:
        """Start the distributor task if it doesn't exist or has completed.

        Args:
            stream_name: Name of the stream topic
        """
        topic = self._topics[stream_name]
        if topic["task"] is None or topic["task"].done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            topic["task"] = loop.create_task(self._distributor(stream_name))

    def add_stream(self, entry: StreamEntry) -> None:
        """Register a stream entry and ensure its topic exists.

        Args:
            entry: Stream entry to register
        """
        self.ensure_topic(entry)

    def publish(self, stream_name: str, item: Any) -> None:
        """Publish an item to a stream topic.

        Args:
            stream_name: Name of the stream topic
            item: Item to publish

        Raises:
            KeyError: If the stream topic doesn't exist
        """
        topic = self._topics.get(stream_name)
        if topic is None:
            raise KeyError(f"Unknown stream: {stream_name}")
        self.start_distributor_if_needed(stream_name)
        topic["publish_queue"].put_nowait(item)

    def subscribe(self, stream_name: str) -> _Subscriber:
        """Subscribe to a stream topic and return a subscriber.

        If replay is enabled, the last published value will be enqueued
        for the new subscriber.

        Args:
            stream_name: Name of the stream topic

        Returns:
            A subscriber instance with its own queue
        """
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
        """Remove a subscriber from a stream topic.

        Args:
            stream_name: Name of the stream topic
            subscriber: Subscriber to remove
        """
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
            dead_subscribers: list[_Subscriber] = []
            entry: StreamEntry = topic["entry"]

            for subscriber in list(subscribers):
                try:
                    if entry.policy == "fifo":
                        await subscriber.queue.put(item)
                    else:
                        subscriber.queue.put_nowait(item)
                except asyncio.QueueFull:
                    try:
                        _ = subscriber.queue.get_nowait()
                    except Exception:
                        pass
                    try:
                        subscriber.queue.put_nowait(item)
                    except Exception:
                        dead_subscribers.append(subscriber)

            for dead_subscriber in dead_subscribers:
                subscribers.discard(dead_subscriber)


class ConnectRouter:
    """Router for Connect-style RPC endpoints."""

    def __init__(self) -> None:
        """Initialize the ConnectRouter with empty registries."""
        self.router = APIRouter()
        self._unaries: Dict[str, ActionEntry] = {}
        self._streams: Dict[str, StreamEntry] = {}
        self.manager = StreamManager()

    def add_unary(self, entry: ActionEntry, service_fqn: str) -> None:
        """Register a unary RPC action endpoint.

        Args:
            entry: Action entry containing the handler function and types
            service_fqn: Fully qualified service name for the path
        """
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
                    if hasattr(input_type, "model_validate"):
                        validated_arg = input_type.model_validate(request_body)
                    else:
                        validated_arg = request_body
                    result = await _maybe_await(entry.func(validated_arg))

                if hasattr(result, "model_dump"):
                    result = result.model_dump()
                return JSONResponse(result or {})
            except Exception as exc:
                return JSONResponse(error_envelope(exc))

    def add_stream(self, entry: StreamEntry, service_fqn: str) -> None:
        """Register a streaming RPC endpoint.

        Args:
            entry: Stream entry containing configuration
            service_fqn: Fully qualified service name for the path
        """
        self._streams[entry.name] = entry
        self.manager.add_stream(entry)

        path = f"/{service_fqn}/{entry.name}"

        async def _stream_iter(subscriber: _Subscriber) -> Any:
            """Async generator yielding Connect frames for each stream item."""
            try:
                while True:
                    stream_item = await subscriber.queue.get()
                    payload = _serialize_stream_item(stream_item)
                    yield _frame(payload)
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_trailer = error_envelope(to_connect_error(exc))
                yield _frame(error_trailer, trailer=True)
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

    def publish(self, stream_name: str, item: Any) -> None:
        """Publish an item to a stream.

        Creates the stream topic if it doesn't exist yet.

        Args:
            stream_name: Name of the stream
            item: Item to publish

        Raises:
            KeyError: If the stream doesn't exist and can't be found
        """
        if stream_name not in self.manager._topics:
            entry = self._streams.get(stream_name)
            if not entry:
                raise KeyError(f"Unknown stream: {stream_name}")
            self.manager.add_stream(entry)
        self.manager.publish(stream_name, item)


def _serialize_stream_item(item: Any) -> Dict[str, Any]:
    if hasattr(item, "model_dump"):
        dumped = item.model_dump()
        if isinstance(dumped, dict):
            return dumped
        return {"value": dumped}
    if isinstance(item, dict):
        return item
    if isinstance(item, list):
        return {"value": item}
    return {"value": item}


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value
