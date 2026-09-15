import json
import os
from contextlib import asynccontextmanager

import aio_pika
from aio_pika.pool import Pool
from fastapi import FastAPI, Request, status
from pydantic import BaseModel, Field

RABBITMQ_URL = os.environ.get(
    "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
)
QUEUE_NAME = os.environ.get("QUEUE_NAME", "fleet-telemetry")


class TelemetryPayload(BaseModel):
    vehicle_id: str
    lat: float
    lng: float
    speed: float = Field(ge=0)
    status: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def get_connection() -> aio_pika.RobustConnection:
        return await aio_pika.connect_robust(RABBITMQ_URL)

    connection_pool = Pool(get_connection, max_size=2)

    async def get_channel() -> aio_pika.Channel:
        async with connection_pool.acquire() as connection:
            return await connection.channel()

    channel_pool = Pool(get_channel, max_size=10)

    async with channel_pool.acquire() as channel:
        await channel.declare_queue(QUEUE_NAME, durable=True)

    app.state.connection_pool = connection_pool
    app.state.channel_pool = channel_pool

    yield

    await channel_pool.close()
    await connection_pool.close()


app = FastAPI(title="Fleet Ingestion Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/telemetry", status_code=status.HTTP_202_ACCEPTED)
async def ingest_telemetry(payload: TelemetryPayload, request: Request):
    message = aio_pika.Message(
        body=json.dumps(payload.model_dump()).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )

    async with request.app.state.channel_pool.acquire() as channel:
        await channel.default_exchange.publish(
            message,
            routing_key=QUEUE_NAME,
        )

    return {"status": "accepted"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
