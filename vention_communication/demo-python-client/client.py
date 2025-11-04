import asyncio
from httpx import AsyncClient, Timeout
from google.protobuf.empty_pb2 import Empty
from proto.app_pb2 import PingRequest
from proto.app_connect import VentionAppServiceClient


async def main():
    timeout = Timeout(connect=10.0, read=None, write=None, pool=None)

    async with AsyncClient(timeout = timeout) as session:
        client = VentionAppServiceClient(
            "http://localhost:8000/rpc",   # address
            proto_json=True,               # use JSON-encoded Connect RPCs
            session=session,               # reuse your httpx.AsyncClient
            timeout_ms=None
        )

        # unary
        res = await client.ping(PingRequest(message="Hello from Python!"))
        print("Ping response:", res.message)

        # stream
        print("Starting heartbeat stream…")
        async for msg in client.heartbeat(Empty()):
            print("Heartbeat value:", msg.value)


if __name__ == "__main__":
    asyncio.run(main())
