# Vention Communication

> A thin, FastAPI-powered RPC layer for machine-apps that exposes Connect-compatible unary and server-streaming endpoints, plus .proto generation from Python decorators—so TS and Python clients get strongly-typed end-to-end contracts.

---

## Table of Contents
- [✨ Features](#-features)
- [🧠 Concepts & Overview](#-concepts--overview)
- [⚙️ Installation & Setup](#-installation--setup)
- [🚀 Quickstart Tutorial](#-quickstart-tutorial)
- [🛠 How-to Guides](#-how-to-guides)
- [📖 API Reference](#-api-reference)
- [🔍 Troubleshooting & FAQ](#-troubleshooting--faq)

## ✨ Features
- **Decorator-based RPCs**: `@action()` for unary; `@stream()` for server streams. Types are inferred from function signatures/Pydantic models and emitted to a .proto
- **Schema-true streams**: Pure payloads only (no heartbeats), latest-wins fan-out, optional replay on subscribe. Strong typing preserved in TS/Python clients
- **Connect JSON wire over HTTP/1.1**: Browser-friendly with proper envelopes/trailers for errors; FastAPI under the hood
- **One service surface**: Routes mounted under `/rpc/<package.Service>/<Method>`, with service name derived from your app name
- **Codegen**: Emits a single `app.proto` including Pydantic models, scalar wrappers for stream payloads, and your service definition

---

## 🧠 Concepts & Overview

**Action (Unary RPC)** — request → response. Input/output types inferred from annotations (Pydantic models or scalars). Missing annotation → treated as `google.protobuf.Empty`.

**Stream (Server streaming)** — downstream fan-out of state/telemetry with no heartbeats; queues are size-1 to ensure freshness (coalescing). On subscribe, optional replay sends the last value immediately if available.

**Service surface** — methods and streams are registered to one service under `/rpc`. The fully-qualified name is calculated from `VentionApp(name=...)`.

**Proto generation** — a `.proto` is built from the decorator registry, including model messages and scalar wrappers for streamed scalars.

---

## ⚙️ Installation & Setup

- Python 3.10+, FastAPI, and Uvicorn required
- `pip install vention-communication` # (your package name here)

**Frontend (TypeScript)**
- We recommend `@connectrpc/connect-web` with `useBinaryFormat: false` for JSON mode

**Python client**
- Use `connectrpc` client (or your wrapper) with an `httpx.AsyncClient` that disables read timeouts for long-idle streams (see Quickstart)

---

## 🚀 Quickstart Tutorial

### 1) Define your RPCs

```python
# demo_server/main.py
from pydantic import BaseModel
from vention_communication.app import VentionApp
from vention_communication.decorators import action, stream
from google.protobuf.empty_pb2 import Empty  # for client code convenience

class PingRequest(BaseModel):
    message: str

class PingResponse(BaseModel):
    message: str

class HeartbeatMessage(BaseModel):
    value: str
    timestamp: int

app = VentionApp(name="VentionApp", emit_proto=True, proto_path="proto/app.proto")

@action()
async def ping(req: PingRequest) -> PingResponse:
    return PingResponse(message=f"Pong: {req.message}")

@stream(name="Heartbeat", payload=HeartbeatMessage)
async def heartbeat_publish() -> HeartbeatMessage:
    # publish one value; you can call this on a schedule/state change
    from time import time
    import random
    return HeartbeatMessage(value=f"{random.random()*100:.2f}", timestamp=int(time()))

app.finalize()  # registers routes under /rpc and emits proto
```

`finalize()` mounts routes under `/rpc` and writes `proto/app.proto`.

**Run:**
```bash
uvicorn demo_server.main:app --reload
```

### 2) Publish to your stream

A simple periodic publisher:

```python
# demo_server/publisher.py (optional)
import asyncio
from .main import heartbeat_publish

async def start_heartbeat_publisher():
    while True:
        await heartbeat_publish()  # fan-out to all subscribers
        await asyncio.sleep(1.0)
```

Mount in startup (e.g., lifespan or background task)—once the app has `finalize()`'d.

### 3) TypeScript client (browser)

```typescript
// client.ts
import { createClient } from "@connectrpc/connect";
import { createConnectTransport } from "@connectrpc/connect-web";
import { VentionAppService } from "./gen/connect/proto/app_connect"; // from buf generate

const transport = createConnectTransport({
  baseUrl: "http://localhost:8000/rpc",
  useBinaryFormat: false,
});
export const client = createClient(VentionAppService, transport);

// usage
const res = await client.ping({ message: "Hello from TS" });
console.log(res.message);

for await (const msg of client.heartbeat({})) {
  // msg: HeartbeatMessage (strongly typed)
  console.log("Heartbeat", msg.value, msg.timestamp);
}
```

### 4) Python client (async)

```python
# client.py
import asyncio
from httpx import AsyncClient, Timeout
from google.protobuf.empty_pb2 import Empty
from proto.app_pb2 import PingRequest
from proto.app_connect import VentionAppServiceClient

async def main():
    timeout = Timeout(connect=10.0, read=None, write=None, pool=None)
    async with AsyncClient(timeout=timeout) as session:
        client = VentionAppServiceClient(
            "http://localhost:8000/rpc",
            proto_json=True,
            session=session,
        )
        res = await client.ping(PingRequest(message="Hello from Python!"))
        print(res.message)
        async for m in client.heartbeat(Empty()):
            print("Heartbeat", m.value, m.timestamp)

asyncio.run(main())
```

---

## 🛠 How-to Guides

### Add a new unary RPC

```python
from pydantic import BaseModel
from vention_communication.decorators import action

class DoThingReq(BaseModel):
    x: int

class DoThingRes(BaseModel):
    ok: bool

@action()
async def do_thing(req: DoThingReq) -> DoThingRes:
    return DoThingRes(ok=req.x > 0)
```

Types are inferred; on `finalize()`, the method is registered and appears in the emitted `.proto`.

### Add a new stream (typed)

```python
from pydantic import BaseModel
from vention_communication.decorators import stream

class SensorState(BaseModel):
    is_present: bool
    sequence: int

@stream(name="Sensor", payload=SensorState)
async def publish_sensor() -> SensorState:
    ...
```

Subscribers connect to `/rpc/<Service>/Sensor` and receive schema-true frames only. Latest-wins coalescing is applied per subscriber.

### Emit the .proto during app startup

```python
app = VentionApp(name="Palletizer", emit_proto=True, proto_path="proto/palletizer.proto")
app.finalize()
```

The service is named `<SanitizedName>Service` in package `vention.app.v1`.

---

## 📖 API Reference

### VentionApp

```python
VentionApp(
  name: str = "VentionApp",
  *,
  emit_proto: bool = False,
  proto_path: str = "proto/app.proto",
  **fastapi_kwargs
)
```

- `.finalize()` — collects decorators, registers routes under `/rpc`, emits `.proto` if enabled, and makes the router available for publisher wrappers

### Decorators

```python
@action(name: Optional[str] = None)
# -> Registers a unary RPC. Input/return types inferred from annotations.

@stream(name: str, payload: type)
# -> Registers a server-streaming RPC. The decorated function doubles as the publisher.
```

Type inference utilities ensure your annotations are present and supported.

### Wire & Routing

- **Base path**: `/rpc`
- **Service FQN**: `vention.app.v1.<ServiceName>Service`
- **Unary**: `POST /rpc/<Service>/<Method>`
- **Stream**: `POST /rpc/<Service>/<StreamName>` → `application/connect+json` frames (JSON)

### Codegen

Writes `proto/app.proto` (or your custom path) from registered RPCs/streams.

Pydantic models become messages; streamed scalars get wrapper messages.

---

## 🔍 Troubleshooting & FAQ

**Q: My TS client gets 404s at `/rpc/vention.app.v1.VentionAppService/Ping`.**

A: The service name comes from `VentionApp(name=...)`. If you changed the app name, your FQN changed. Regenerate the client or point it to the new service FQN.

**Q: Publishing raises `KeyError: Unknown stream` on startup.**

A: You're publishing before `finalize()` (which registers topics) or before first subscriber triggered async init; ensure `finalize()` ran and use the published decorator function after startup.

**Q: Python client stream dies with `ReadTimeout` / `DEADLINE_EXCEEDED`.**

A: Streams are idle-friendly. Create your `httpx.AsyncClient` with `Timeout(read=None)` and avoid per-call deadlines for long-lived streams (see Quickstart).

**Q: Do streams send heartbeats?**

A: No. We keep the wire strictly schema-true. If you need liveness signals, publish explicit heartbeat messages as part of your own model.

**Q: Can I serve multiple subscribers?**

A: Yes—fan-out is built in with coalescing per subscriber (queue size 1). It favors latest state over backlog.

**Q: Where do Connect error envelopes come from?**

A: Errors from unary/stream handlers are wrapped and surfaced via JSON envelopes/trailers, compatible with Connect JSON clients. (See router internals.)

---