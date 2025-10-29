import random
import asyncio
import time
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from src.vention_communication import VentionApp, action, stream

app = VentionApp(title="Demo")

# Enable CORS for browser testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Ping (Unary RPC)
# -------------------------------
class PingRequest(BaseModel):
    message: str


class PingResponse(BaseModel):
    message: str
    
class HeartbeatMessage(BaseModel):
    value: str
    timestamp: int


@action()
async def ping(req: PingRequest) -> PingResponse:
    return {"message": f"Pong: {req.message}"}


# -------------------------------
# Heartbeat (Server Stream)
# -------------------------------
@stream(name="heartbeat", payload=HeartbeatMessage)
async def heartbeat():
    """Publisher function — every call broadcasts to all subscribers."""
    value = round(random.uniform(0, 100), 2)
    return HeartbeatMessage(value=str(value), timestamp=int(time.time()))


# -------------------------------
# Background publisher task
# -------------------------------
@app.on_event("startup")
async def start_heartbeat_publisher():
    """Periodically call the heartbeat() publisher once per second."""
    async def publish_loop():
        while True:
            await heartbeat()  # broadcast to all connected subscribers
            await asyncio.sleep(5)

    asyncio.create_task(publish_loop())


# -------------------------------
# Finalize app
# -------------------------------
app.finalize(emit_proto=True)
