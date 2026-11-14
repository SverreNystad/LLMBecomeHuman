# Developer Setup

## Prerequisites

Before you can start developing, make sure you have the following installed:

- **Git**: Ensure that git is installed on your machine. [Download Git](https://git-scm.com/downloads)
- **Docker**: Ensure that Docker is installed on your machine. [Download Docker](https://www.docker.com/products/docker-desktop)
- **Python**: Ensure that Python 3.8 or higher is installed on your machine. [Download Python](https://www.python.org/downloads/)
- **UV**: Ensure that [uv](https://github.com/astral-sh/uv) is installed on your machine. [Download UV](https://github.com/astral-sh/uv)
- **pre-commit**: Ensure that [pre-commit](https://pre-commit.com/) is installed on your machine. [Download pre-commit](https://pre-commit.com/)

### Run Pre-commit Hooks

```bash
uv run pre-commit run --all-files
```

### Generate Documentation Site

To build and preview the documentation site locally:

```bash
uv run mkdocs build
uv run mkdocs serve
```

This will build the documentation and start a local server at [http://127.0.0.1:8000/](http://127.0.0.1:8000/) where you can browse the docs and API reference. Get the documentation according to the latest commit on main by viewing the `gh-pages` branch on GitHub: [https://sverrenystad.github.io/LLMBecomeHuman/](sverrenystad.github.io/LLMBecomeHuman/).

## Kubernetes (Helm)

The Helm chart in `k8s/` deploys the dashboard image. It ships with three values files that are layered on top of each other:

| File                         | Purpose                                                                                                                             |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `k8s/values.yaml`            | Chart defaults shared by every environment. Always applied by Helm.                                                                 |
| `k8s/local_values.yaml`      | Local cluster (minikube): image built locally, no public exposure.                                                                  |
| `k8s/production_values.yaml` | Public deployment: CI-published image from GHCR, exposed at [llmbecomehuman.com](https://llmbecomehuman.com) via Cloudflare Tunnel. |

Pass exactly one environment file with `-f`. Helm merges it over `values.yaml`, and any `--set` flag wins over both.

> **Warning: always pass the values file.** `helm upgrade` does **not** remember values from the previous release. Running it without `-f` resets the release to the plain `values.yaml` defaults, which, for example, turns the Cloudflare Tunnel off and takes the site down (Cloudflare error 1033).

### Extra prerequisites

- **kubectl**: [Install kubectl](https://kubernetes.io/docs/tasks/tools/)
- **Helm**: [Install Helm](https://helm.sh/docs/intro/install/)
- **minikube** (for local development): [Install minikube](https://minikube.sigs.k8s.io/docs/start/)

### Local development

Build the image directly into minikube, so no registry is needed, and install the chart:

```bash
minikube start
minikube image build -t llm-become-human:local .
helm upgrade --install llmbecomehuman ./k8s -f k8s/local_values.yaml
```

Open the dashboard through a port-forward:

```bash
kubectl port-forward svc/llmbecomehuman-llm-become-human 8080:80
```

Then visit [http://127.0.0.1:8080](http://127.0.0.1:8080). The health endpoint is at `/api/health`.

After changing code, rebuild and restart. The tag stays `local`, so Helm sees no change on its own:

```bash
minikube image build -t llm-become-human:local .
kubectl rollout restart deploy/llmbecomehuman-llm-become-human
```

### Production

Production runs the image that CI pushes to `ghcr.io/sverrenystad/llmbecomehuman` on every push to `main`. A `cloudflared` pod opens an outbound tunnel to Cloudflare, so the cluster needs no public IP or ingress controller.

**One-time setup:**

1. In the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels**, create a *Cloudflared* tunnel and copy its token.
1. Store the token in the cluster. Never commit it:
   ```bash
   kubectl create secret generic cloudflared-token --from-literal=token='<TOKEN>'
   ```
1. On the tunnel's **Routes** tab, add a published application for `llmbecomehuman.com` and another for `www.llmbecomehuman.com`, both with the service URL:
   ```
   http://llmbecomehuman-llm-become-human.default.svc.cluster.local:80
   ```
   Cloudflare creates the DNS records automatically. This URL assumes the release is named `llmbecomehuman` and installed in the `default` namespace.

**Deploy:**

```bash
helm upgrade --install llmbecomehuman ./k8s -f k8s/production_values.yaml
```

`latest` is pulled again on every pod start. To roll out or roll back to a specific commit, pin its tag:

```bash
helm upgrade --install llmbecomehuman ./k8s -f k8s/production_values.yaml --set image.tag=sha-abc1234
```

**Automatic redeploys with Keel:**

Kubernetes never checks the registry for a running pod, so a new `latest` from CI isn't picked up on its own. [Keel](https://keel.sh) runs in the cluster, polls GHCR (every 5 minutes, set by `keel.pollSchedule`) and rolls out the Deployment when the image behind `latest` changes. `production_values.yaml` turns this on with `keel.enabled: true`, which adds the `keel.sh/*` annotations to the Deployment. The Keel controller itself is installed once per cluster:

```bash
helm repo add keel https://charts.keel.sh
helm repo update
helm upgrade --install keel keel/keel --namespace keel --create-namespace --set helmProvider.enabled=false
```

`helmProvider.enabled=false` makes Keel act on the Deployment annotations only, instead of also managing Helm releases. Watch it work with `kubectl -n keel logs deploy/keel -f`. To redeploy straight away instead of waiting for the next poll, run `kubectl rollout restart deploy/llmbecomehuman-llm-become-human`.

**Verify:**

```bash
kubectl get pods
kubectl logs deploy/llmbecomehuman-llm-become-human-cloudflared | grep "Registered tunnel connection"
curl https://llmbecomehuman.com/api/health
```

### Troubleshooting

| Symptom                                  | Likely cause                                                                                                                                         |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Probes fail with `connection refused`    | `containerPort` doesn't match the port the app listens on (8000).                                                                                    |
| Pod stuck in `ErrImageNeverPull` (local) | The image hasn't been built into minikube yet. Run `minikube image build -t llm-become-human:local .`                                                |
| Cloudflare error 1033                    | No `cloudflared` pod is connected. Check that the release was deployed with `production_values.yaml` and that the `cloudflared-token` Secret exists. |
| Cloudflare error 502                     | The tunnel is up but can't reach the Service. Check the service URL on the tunnel route and `kubectl get svc`.                                       |
