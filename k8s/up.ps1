$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$clusterList = k3d cluster list 2>$null | Out-String
if ($clusterList -notmatch "(?m)^fleet\b") {
    k3d cluster create --config k8s/local/k3d.yaml
}

docker build -t fleet/ingestion:local ./ingestion_service
docker build -t fleet/worker:local ./worker_service
docker build -t fleet/websocket:local ./websocket_service
docker build -t fleet/frontend:local ./frontend

k3d image import `
    fleet/ingestion:local `
    fleet/worker:local `
    fleet/websocket:local `
    fleet/frontend:local `
    -c fleet

kubectl apply -k k8s/local
kubectl -n fleet rollout status deployment/ingestion --timeout=180s
kubectl -n fleet rollout status deployment/worker --timeout=180s
kubectl -n fleet rollout status deployment/websocket --timeout=180s
kubectl -n fleet rollout status deployment/frontend --timeout=180s

Write-Host ""
Write-Host "Dashboard:  http://localhost:8080"
Write-Host "Ingest:     http://localhost:8080/telemetry"
Write-Host "WebSocket:  ws://localhost:8080/ws/fleet"
Write-Host ""
kubectl -n fleet get pods,svc,ingress
