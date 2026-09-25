# Day 3 local Kubernetes deployment evidence

- Observed: 2026-09-24T04:46:19Z; environment: kind `insighthub` / namespace `insighthub-prod`; `aws_used=false`.
- Helm 3.22.0; release `insighthub` revision 3, status `deployed`. Source base commit `df975b653ba3`; worker image `df975b653ba3-local2` includes the uncommitted ARQ logging fix. Do not treat these local tags as a CI source binding.
- `helm lint` PASS for `values-local.yaml` and `values-eks.yaml`; `helm template` and Kubernetes client dry-run PASS. EKS render contains the three app Deployments and two Services, with no local DB/Redis StatefulSets or PVCs.
- `kubectl get pods,deploy,sts,svc,pvc -n insighthub-prod`: five pods `1/1 Running`, three Deployments `1/1`, two StatefulSets `1/1`, four Services and two bound PVCs. All five rollout status checks PASS.
- Redis `redis-cli ping` → `PONG`; PostgreSQL `pg_isready -U insighthub -d insighthub` → accepting connections. API `/readyz` also validates schema and vector dimension.
- Via localhost port-forward, web `/` → 200 and API `/healthz` → 200. `python scripts/smoke-k8s-local.py --api-url http://127.0.0.1:18000 --web-url http://127.0.0.1:13000 --poll-timeout 30` → PASS, document ID 3: upload 202, same-ID poll reaches `ready` with chunks within the 30-second budget, `/chat` 200 with answer/sources/contexts, metrics valid. Fixture mode only; uploaded sample is retained in the local PostgreSQL PVC.
- After enabling ARQ custom logging, `kubectl logs deployment/insighthub-worker --tail=20` showed only the sanitized `ingestion_completed` JSON record for document 3; no job arguments/document bytes.
- Regression: `make test-backend` 51 tests PASS; verifier unit suite 57 tests PASS; `git diff --check` PASS. Local Helm result does not verify AWS, HTTPS, OIDC or real-provider quality.
