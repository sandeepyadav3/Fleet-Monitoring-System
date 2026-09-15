#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! k3d cluster list | awk 'NR>1 {print $1}' | grep -qx fleet; then
  k3d cluster create --config k8s/local/k3d.yaml
fi

docker build -t fleet/ingestion:local ./ingestion_service
docker build -t fleet/worker:local ./worker_service
docker build -t fleet/websocket:local ./websocket_service
docker build -t fleet/frontend:local ./frontend

k3d image import \
  fleet/ingestion:local \
  fleet/worker:local \
  fleet/websocket:local \
  fleet/frontend:local \
  -c fleet

kubectl apply -k k8s/local
kubectl -n fleet rollout status deployment/ingestion --timeout=180s
kubectl -n fleet rollout status deployment/worker --timeout=180s
kubectl -n fleet rollout status deployment/websocket --timeout=180s
kubectl -n fleet rollout status deployment/frontend --timeout=180s

echo
echo "Dashboard:  http://localhost:8080"
echo "Ingest:     http://localhost:8080/telemetry"
echo "WebSocket:  ws://localhost:8080/ws/fleet"
echo
kubectl -n fleet get pods,svc,ingress
