# Fleet Monitoring System

Event-driven platform that ingests live vehicle telemetry, persists it for history, and streams current positions to a map dashboard with sub-second freshness.

Built as a set of independently deployable services — not a monolith with a message broker bolted on. The ingest path never waits on MongoDB or the UI; the UI never talks to the queue.

**Stack:** FastAPI · Next.js (App Router) · RabbitMQ · Redis · MongoDB · Leaflet · Docker Compose · Kubernetes (k3d + Kustomize)

---

## Problem

A fleet of ~50 vehicles emits GPS and status every few seconds. Three consumers need that data for different reasons:

| Consumer | Needs | Latency tolerance |
|---|---|---|
| Dispatch map | Latest position only | ~1s |
| Ops / audit | Full history | Minutes |
| Ingest API | Accept load spikes without blocking vehicles | Immediate 202 |

Putting all three on one request path couples availability. This repo splits **write-ahead messaging**, **hot state**, and **cold history**.

---

## Architecture

```
┌─────────────┐     POST /telemetry      ┌──────────────────────┐
│  Simulator  │ ───────────────────────► │  Ingestion (FastAPI) │
│  50 vehicles│      HTTP 202            │  aio-pika publisher  │
└─────────────┘                          └──────────┬───────────┘
                                                    │ persistent publish
                                                    ▼
                                         ┌──────────────────────┐
                                         │  RabbitMQ            │
                                         │  queue: fleet-telemetry
                                         └──────────┬───────────┘
                                                    │ manual ack
                                                    ▼
                                         ┌──────────────────────┐
                                         │  Worker (pika)       │
                                         │  at-least-once       │
                                         └───┬──────────────┬───┘
                             SET vehicle:{id}│              │ insert + server_timestamp
                                             ▼              ▼
                                      ┌──────────┐   ┌─────────────┐
                                      │  Redis   │   │  MongoDB    │
                                      │  hot     │   │  fleet_db   │
                                      │  state   │   │  telemetry_ │
                                      └────┬─────┘   │  logs       │
                                           │         └─────────────┘
                              SCAN + diff  │  (only while a client is connected)
                                           ▼
                                      ┌──────────────────────┐
                                      │  WebSocket service   │
                                      │  snapshot / update   │
                                      └──────────┬───────────┘
                                                 │ ws://…/ws/fleet
                                                 ▼
                                      ┌──────────────────────┐
                                      │  Next.js dashboard   │
                                      │  Leaflet markers     │
                                      └──────────────────────┘
```

**Local infrastructure** (Compose): MongoDB `:27017`, Redis `:6379`, RabbitMQ AMQP `:5672` + management UI `:15672`.

---

## Design decisions

These are the choices that keep the system correct under load, not just green on a happy path.

### 1. Ingest is fire-and-forget (202 + durable queue)

`POST /telemetry` validates the payload, publishes a **persistent** AMQP message, and returns `202 Accepted`. The HTTP request does not open Mongo or wait for a consumer. Vehicles keep reporting if the worker or dashboard is down.

The publisher uses an **aio-pika connection/channel pool** tied to the FastAPI lifespan — connections are opened once, not per request.

### 2. At-least-once delivery, not at-most-once

The worker **acks only after both Redis and Mongo succeed**. Transient DB errors `nack` + requeue. Poison messages (invalid JSON, missing `vehicle_id`) are `nack`ed **without** requeue so they cannot livelock the queue.

Tradeoff: a crash between Mongo insert and ack can duplicate a history row. That is accepted for telemetry; the live map key is overwritten, so Redis stays idempotent per vehicle.

### 3. Redis is latest-state, Mongo is the log

| Store | Shape | Grows with |
|---|---|---|
| Redis `vehicle:{id}` | One JSON blob per vehicle | Fleet size (~50 keys), not message volume |
| Mongo `fleet_db.telemetry_logs` | One document per ping + UTC `server_timestamp` | Time |

A full day with the dashboard closed does **not** fill Redis RAM. The worker `SET`s the same keys. Unbounded growth is on Mongo (retention / TTL index would be the next production control).

### 4. Push to the UI is pull-from-Redis, not queue fan-out

The websocket service does **not** subscribe to RabbitMQ. The map is a **read model**: poll `vehicle:*` every 1s **only while a browser holds `/ws/fleet`**. No dashboard tab ⇒ no SCAN. First frame is a full `snapshot`; later frames are diffs (`update` + `removed`) so the client is not flooded with unchanged vehicles.

Polling vs Redis keyspace notifications: polling is operationally simpler locally (no `notify-keyspace-events` config) and is enough at this cardinality. Pub/sub would be the next step if fleet size or freshness SLOs demanded it.

### 5. Frontend treats Leaflet as a browser-only resource

Next.js App Router still SSRs client components. Leaflet needs `window`. The map is loaded with `next/dynamic(..., { ssr: false })`, markers keep a stable React `key` per `vehicle_id`, and position updates go through `setLatLng` so markers **move** instead of remounting.

---

## Repository layout

```
├── docker-compose.yml          # Mongo, Redis, RabbitMQ (laptop)
├── ingestion_service/          # HTTP edge → AMQP
│   ├── api.py
│   └── simulator.py            # 50 vehicles, ~2s cadence
├── worker_service/             # AMQP → Redis + Mongo
│   └── worker.py
├── websocket_service/          # Redis read model → WebSocket
│   └── server.py
├── frontend/                   # Next.js 16, TypeScript, Tailwind, react-leaflet
└── k8s/                        # k3d cluster: StatefulSets, Deployments, Ingress
```

---

## Quick start

Requires Docker, Python 3.12+, and Node 20+.

**1. Infrastructure**

```bash
docker compose up -d
```

RabbitMQ UI: [http://localhost:15672](http://localhost:15672) (`guest` / `guest`). Queue name: `fleet-telemetry`. Depth near **0** while the worker is healthy is expected — messages are not a log; they are a buffer. Use **Message rates** to see traffic.

**2. Services** (separate terminals)

Ports below avoid colliding ingest HTTP with the WebSocket server:

```bash
# Ingest API
cd ingestion_service
pip install -r requirements.txt
python -m uvicorn api:app --reload --port 8001

# Worker
cd worker_service
pip install -r requirements.txt
python worker.py

# Live map feed
cd websocket_service
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 8000

# Dashboard
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Confirm `Client connected to /ws/fleet` in the websocket terminal.

**3. Load**

```bash
cd ingestion_service
python simulator.py
```

Simulator posts to `http://127.0.0.1:8001/telemetry` and wanders around **Des Moines, IA** (`41.5868, -93.6250`). Pan/zoom the map there if the default Leaflet center is elsewhere — markers exist even when they are off-screen.

---

## Kubernetes (k3d)

The same services run on a local k3s cluster via **Kustomize**: StatefulSets + PVCs for Mongo/Redis/RabbitMQ, Deployments for apps, init containers so brokers are up before clients start, and Traefik Ingress on **http://localhost:8080**.

```powershell
./k8s/up.ps1
```

```bash
./k8s/up.sh
```

In-cluster DNS replaces `localhost` (`amqp://fleet:fleet@rabbitmq:5672/` — RabbitMQ’s default `guest` user is loopback-only). The worker stays at **one replica** until competing-consumer semantics are designed. Full notes: [k8s/README.md](k8s/README.md).

---

## API and wire formats

**Ingest** `POST /telemetry`

```json
{
  "vehicle_id": "Harvester-10",
  "lat": 41.59,
  "lng": -93.62,
  "speed": 24.1,
  "status": "moving"
}
```

**WebSocket** `ws://localhost:8000/ws/fleet`

```json
{ "type": "snapshot", "vehicles": [ { "vehicle_id": "…", "lat": 0, "lng": 0, "speed": 0, "status": "moving" } ] }
{ "type": "update", "vehicles": [ { "…" : "changed payload" } ], "removed": [] }
```

---

## Production follow-ups (not in this repo)

The Compose and k3d stacks are laptop-sized. A production cut would add auth on ingest and WS, TLS on Ingress, TTL on Redis keys so silent vehicles leave the map, a Mongo TTL/time-series retention policy, structured tracing across publish → consume → persist, and replacing SCAN polling with Redis pub/sub or keyspace notifications at larger fleet sizes.
