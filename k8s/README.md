# Kubernetes (k3d)

Local cluster manifests for the same service boundaries as Docker Compose: stateful data plane, stateless ingest, a single worker replica, and an Ingress that keeps HTTP, WebSocket, and the UI on one host.

This is a **laptop-sized** cluster (k3s in Docker), not a production GKE/EKS chart. The point is working Deployments, StatefulSets, probes, ConfigMaps, and in-cluster DNS.

## Prerequisites

- Docker
- [k3d](https://k3d.io) (`winget install k3d` / `brew install k3d`)
- `kubectl` (k3d can install a kubeconfig for you)

## Bring it up

From the repo root:

```powershell
# Windows
./k8s/up.ps1
```

```bash
# macOS / Linux
chmod +x k8s/up.sh
./k8s/up.sh
```

The script creates cluster `fleet` (if missing), builds app images, imports them into k3d (no registry required), and applies `k8s/local`.

Then open [http://localhost:8080](http://localhost:8080). Pan the map to Des Moines, IA (`41.59, -93.62`). The in-cluster simulator posts to `http://ingestion/telemetry` automatically.

```bash
kubectl -n fleet get pods
kubectl -n fleet logs deploy/worker -f
```

Tear down:

```bash
k3d cluster delete fleet
```

## Layout

```
k8s/
  base/                 # cluster-agnostic workloads
    mongodb.yaml        # StatefulSet + PVC
    redis.yaml
    rabbitmq.yaml       # non-guest user (guest is loopback-only)
    ingestion.yaml      # Deployment + /healthz probes
    worker.yaml         # replicas: 1
    websocket.yaml
    frontend.yaml
    simulator.yaml
    configmap.yaml      # amqp://…@rabbitmq — not localhost
  local/                # k3d overlay
    ingress.yaml        # Traefik: /telemetry, /ws, /
    k3d.yaml            # 8080 → load balancer :80
```

Apply without the helper script:

```bash
k3d cluster create --config k8s/local/k3d.yaml
# build + k3d image import … (see up.sh)
kubectl apply -k k8s/local
```

## Why these shapes

| Workload | Kind | Notes |
|---|---|---|
| Mongo, Redis, RabbitMQ | StatefulSet + PVC | Identity and disk; k3d uses the local-path provisioner |
| Ingestion, websocket, frontend | Deployment | Stateless; scale later |
| Worker | Deployment **replicas: 1** | Competing consumers need an explicit prefetch/idempotency story first |
| Simulator | Deployment | Same ingest image, different command |

App pods use **init containers** (`nc`) so they do not crash-loop before brokers are listening.

**RabbitMQ `guest` is not used in-cluster.** The broker rejects `guest` from non-loopback addresses. Manifests create user `fleet` / `fleet` and ConfigMap `RABBITMQ_URL=amqp://fleet:fleet@rabbitmq:5672/`.

**Ingress paths** (Traefik, bundled with k3s):

| Path | Service |
|---|---|
| `/telemetry` | ingestion |
| `/ws` | websocket |
| `/` | frontend |

The frontend image is built with `NEXT_PUBLIC_WS_URL=ws://localhost:8080/ws/fleet` so the browser hits the same origin the Ingress exposes.

## What this is not

No NetworkPolicies, no TLS, no HPA, no Helm, no managed cloud storage class. Those are the usual next steps once this overlay is running.
