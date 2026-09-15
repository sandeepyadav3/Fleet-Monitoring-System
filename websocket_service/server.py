import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
VEHICLE_KEY_PATTERN = "vehicle:*"
POLL_INTERVAL_SECONDS = 1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("fleet-websocket")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    await client.ping()
    app.state.redis = client
    logger.info("Connected to Redis at %s:%s", REDIS_HOST, REDIS_PORT)
    yield
    await client.aclose()


app = FastAPI(title="Fleet WebSocket Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


async def fetch_vehicles(client: redis.Redis) -> dict[str, dict]:
    keys = [key async for key in client.scan_iter(match=VEHICLE_KEY_PATTERN)]
    if not keys:
        return {}

    vehicles: dict[str, dict] = {}
    values = await client.mget(keys)
    for key, raw in zip(keys, values):
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Skipping invalid JSON at Redis key %s", key)
            continue
        vehicle_id = payload.get("vehicle_id") or key.removeprefix("vehicle:")
        vehicles[vehicle_id] = payload
    return vehicles


def diff_state(
    previous: dict[str, dict],
    current: dict[str, dict],
) -> tuple[list[dict], list[str]]:
    updated = [
        payload
        for vehicle_id, payload in current.items()
        if previous.get(vehicle_id) != payload
    ]
    removed = [
        vehicle_id for vehicle_id in previous if vehicle_id not in current
    ]
    return updated, removed


@app.websocket("/ws/fleet")
async def fleet_socket(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected to /ws/fleet")
    redis_client: redis.Redis = websocket.app.state.redis
    previous: dict[str, dict] = {}
    sent_snapshot = False

    try:
        while True:
            current = await fetch_vehicles(redis_client)

            if not sent_snapshot:
                await websocket.send_json(
                    {"type": "snapshot", "vehicles": list(current.values())}
                )
                sent_snapshot = True
            else:
                updated, removed = diff_state(previous, current)
                if updated or removed:
                    await websocket.send_json(
                        {
                            "type": "update",
                            "vehicles": updated,
                            "removed": removed,
                        }
                    )

            previous = current
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        logger.info("Client disconnected from /ws/fleet")
    except Exception:
        logger.exception("WebSocket error; closing connection")
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)
