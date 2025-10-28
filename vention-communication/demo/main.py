# demo/main.py
import random
import asyncio
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


@action()
async def ping(req: PingRequest) -> PingResponse:
    return {"message": f"Pong: {req.message}"}


# -------------------------------
# Heartbeat (Server Stream)
# -------------------------------
@stream(name="heartbeat", payload=str)
async def heartbeat():
    value = round(random.uniform(0, 100), 2)
    return str(value)



# -------------------------------
# Finalize app
# -------------------------------
app.finalize(emit_proto=True)
