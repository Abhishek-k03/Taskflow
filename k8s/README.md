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
| images | `:latest`, local | `:latest`, `imagePullPolicy: IfNotPresent` | registry, pinned to `1.0.0` |

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

## Verified against a live cluster

Applied to Docker Desktop's Kubernetes (`desktop-control-plane`, v1.34.3)
with the `dev` overlay. All pods reached Ready, and in-cluster: a task
submitted to the `api` Service was executed by a `worker` pod and returned
its result; a running task was cancelled and resolved to `CANCELLED`;
`/health` aggregated worker heartbeats across pods even though the api pod
runs no workers of its own; the scheduler acquired the Redis leader lock;
and the frontend Service served both `/` and the `/api` proxy.

Two things the apply caught that `kubectl kustomize` could not:

- **`imagePullPolicy: Never` broke every pod.** `Never` assumes the image is
  already in the node's own store, which holds after `kind load
  docker-image` but not on Docker Desktop, whose node pulls through a mirror
  serving the host's images. Every workload came up `ErrImageNeverPull`.
  Now `IfNotPresent`, which works on both. The same patch was also
  Deployment-only, so the migrate Job fell through to Kubernetes' default of
  `Always` for a `:latest` tag.
- **The frontend readiness probe was too tight.** `/` is a server-rendered
  route and the probe used the default 1s timeout, so a pod serving in 127ms
  still took about a minute to go Ready. Now `timeoutSeconds: 5`.

To reproduce:

1. Enable Kubernetes in Docker Desktop (Settings, then Kubernetes), or
   `choco install kind` and `kind create cluster`.
2. Build the images under the names the manifests reference:
   `docker build -t taskflow-backend:latest ./taskflow`
   `docker build -t taskflow-frontend:latest ./frontend`
   (with `kind`, also `kind load docker-image taskflow-backend:latest`)
3. `kubectl apply -k k8s/overlays/dev`
4. `kubectl -n taskflow wait --for=condition=available deploy --all --timeout=300s`

### Redeploying after a code change

`:latest` with `imagePullPolicy: IfNotPresent` will **not** pick up a rebuilt
image. The node already has something tagged `taskflow-backend:latest`, so it
keeps using it - the pods restart and quietly run the old code, which is
exactly as confusing as it sounds. It was caught here by a fix that was
provably in the image and provably not in the cluster.

With `kind`, `kind load docker-image` overwrites the node's copy, so a rebuild
is picked up. On Docker Desktop nothing overwrites it. Use a unique tag:

```bash
TAG=$(date +%s)
docker build -t taskflow-backend:$TAG ./taskflow
kubectl -n taskflow set image deploy/api api=taskflow-backend:$TAG
kubectl -n taskflow set image deploy/worker worker=taskflow-backend:$TAG
```

or, to keep it in the overlay:

```bash
cd k8s/overlays/dev && kustomize edit set image taskflow-backend=taskflow-backend:$TAG
```

Re-applying over a **completed** migrate Job fails with `field is immutable`
- a Job's pod template cannot be changed once it exists. Run
`kubectl -n taskflow delete job migrate` first.

The Ingress additionally needs an ingress-nginx controller installed.
