# BOS Kubernetes manifests (Phase 1 deliverable #12)

Apply with: `kubectl apply -f deploy/k8s/`

## Notes

- Single-service deployment (web + API in one image, no separate worker process yet)
- PVC `bos-data` persists SQLite + ChromaDB across pod restarts
- Secret `bos-secrets` must be created out-of-band:
  `kubectl create secret generic bos-secrets --from-literal=bos-api-key=...`
- For production split into separate Deployments (api / worker / scheduler)
  behind an Internal LoadBalancer + Cloud Armor / WAF.
