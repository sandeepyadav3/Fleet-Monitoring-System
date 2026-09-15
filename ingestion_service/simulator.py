import asyncio
import os
import random

import aiohttp

TELEMETRY_URL = os.environ.get(
    "TELEMETRY_URL", "http://127.0.0.1:8001/telemetry"
)
INTERVAL_SECONDS = 2
VEHICLE_COUNT = 50

# Depot coordinates; each vehicle wanders nearby from its own start point.
DEPOT_LAT = 34.0698 
DEPOT_LNG = -118.2628

STATUSES = ("moving", "idle", "stopped")

VEHICLE_IDS = (
    [f"Tractor-{i:02d}" for i in range(1, 16)]
    + [f"Fuel-{i:02d}" for i in range(1, 13)]
    + [f"Truck-{i:02d}" for i in range(1, 14)]
    + [f"Harvester-{i:02d}" for i in range(1, 11)]
)


def initial_position() -> tuple[float, float]:
    return (
        DEPOT_LAT + random.uniform(-0.02, 0.02),
        DEPOT_LNG + random.uniform(-0.02, 0.02),
    )


def drift(lat: float, lng: float) -> tuple[float, float]:
    return (
        lat + random.uniform(-0.0008, 0.0008),
        lng + random.uniform(-0.0008, 0.0008),
    )


def build_payload(vehicle_id: str, lat: float, lng: float) -> dict:
    status = random.choices(STATUSES, weights=(0.7, 0.2, 0.1), k=1)[0]
    speed = 0.0 if status != "moving" else round(random.uniform(8.0, 85.0), 1)
    return {
        "vehicle_id": vehicle_id,
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "speed": speed,
        "status": status,
    }


async def post_telemetry(
    session: aiohttp.ClientSession,
    payload: dict,
) -> None:
    try:
        async with session.post(TELEMETRY_URL, json=payload) as response:
            if response.status != 202:
                body = await response.text()
                print(
                    f"Unexpected status {response.status} for "
                    f"{payload['vehicle_id']}: {body}"
                )
    except aiohttp.ClientError as exc:
        print(f"Failed to post {payload['vehicle_id']}: {exc}")


async def run_simulator() -> None:
    if len(VEHICLE_IDS) != VEHICLE_COUNT:
        raise RuntimeError(
            f"Expected {VEHICLE_COUNT} vehicles, got {len(VEHICLE_IDS)}"
        )

    positions = {vehicle_id: initial_position() for vehicle_id in VEHICLE_IDS}

    async with aiohttp.ClientSession() as session:
        print(
            f"Simulating {VEHICLE_COUNT} vehicles every "
            f"{INTERVAL_SECONDS}s -> {TELEMETRY_URL}"
        )
        while True:
            payloads = []
            for vehicle_id in VEHICLE_IDS:
                lat, lng = drift(*positions[vehicle_id])
                positions[vehicle_id] = (lat, lng)
                payloads.append(build_payload(vehicle_id, lat, lng))

            await asyncio.gather(
                *(post_telemetry(session, payload) for payload in payloads)
            )
            await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(run_simulator())
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
