# Kubernetes manifests

Kustomize base plus `dev` and `prod` overlays.

```bash
kubectl apply -k k8s/overlays/dev     # local cluster
kubectl apply -k k8s/overlays/prod    # pinned images, real replica counts
```

## What the overlays change

| | base | dev | prod |
|---|---|---|---|
| api / worker / frontend replicas | 2 / 2 / 2 | 1 / 1 / 1 | 3 / 4 / 2 |
| HPA + PodDisruptionBudget | yes | removed | yes |
| images | `:latest`, local | `:latest`, `imagePullPolicy: Never` | registry, pinned to `1.0.0` |

`dev` drops the HPA and PDB because a one-node cluster has nothing to
autoscale onto and a PDB with one replica blocks node drains.

## Notes on specific choices

- **Liveness hits `/health/live`, which checks no dependencies.** Kubernetes
  restarts pods that fail liveness, so pointing it at a check that touches
  Redis or Postgres would turn a brief dependency blip into a cluster-wide
  restart storm. `/health/ready` is the one that checks dependencies, and
  failing it only removes the pod from the Service.
- **The scheduler is `replicas: 1` with `strategy: Recreate`.** The Redis
  leader lock makes an accidental overlap safe rather than double-firing
  every cron job, but there is still no reason to run two.
- **Workers get `terminationGracePeriodSeconds: 120`** so an in-flight task
  can finish. Anything still unacked when the pod goes is reclaimed by
  another worker through `XAUTOCLAIM`.
- **The HPA scales on CPU.** Queue depth is the better signal and the app
  already publishes it as `taskflow_queue_depth`, but consuming it requires
  the Prometheus Adapter to serve `external.metrics.k8s.io`. The External
  metric block is in `worker.yaml`, commented, ready to swap in once the
  adapter is installed.
- **`/api` and `/ws` route to the frontend, not straight to the api.** The
  Next server is what attaches the API key and preserves the same-origin
  contract the browser depends on.
- **The Secret in `config.yaml` is a placeholder.** Real deployments should
  source it from a secret manager rather than a manifest in git.

## Not yet verified against a live cluster

These manifests build cleanly (`kubectl kustomize`) and pass structural
checks, but they have **not** been applied to a running cluster - none is
available on this machine (`kind`, `minikube`, `k3d` and `helm` are all
absent, and Docker Desktop's Kubernetes has never been enabled).

To actually try them:

1. Enable Kubernetes in Docker Desktop (Settings → Kubernetes), or
   `choco install kind` and `kind create cluster`.
2. Build the images so `imagePullPolicy: Never` can find them:
   `docker build -t taskflow-backend:latest ./taskflow`
   `docker build -t taskflow-frontend:latest ./frontend`
   (with `kind`, also `kind load docker-image taskflow-backend:latest`)
3. `kubectl apply -k k8s/overlays/dev`
4. `kubectl -n taskflow wait --for=condition=available deploy --all --timeout=300s`

The Ingress additionally needs an ingress-nginx controller installed.
