# archive/

Work that is deliberately parked, kept because it is a useful starting point
rather than because it works. Nothing here is wired into the build, CI or
deployment, and nothing here should be assumed to run.

## `helm-wip/` — Kubernetes chart (WIP)

A partial Helm chart for the platform. It covers three of the fourteen
services (backend, convertor, frontend) and is **not deployable**:

- no manifests for postgres, redis, rabbitmq, minio, elasticsearch, vault,
  nginx or the monitoring stack;
- the deployments it does have carry no env, no readiness/liveness probes
  and no resource limits;
- `templates/ingress.yaml` reads values that `values.yaml` never defines.

Kubernetes is not the deployment target: the platform runs on Docker
Compose (see the root README), which handles all fourteen services on one
host. Finishing the chart would take considerably longer than the value it
adds at this stage, and a half-written chart in the repository root implied
a readiness that did not exist.

If Kubernetes ever becomes the target, start from here rather than from
scratch -- but treat every file as a draft to be reviewed, not as
configuration that once worked.
