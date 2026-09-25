# Local KIND cluster for the Kubernetes MCP

`kubernetes/kind/insighthub.yaml` creates one local KIND control plane with a
stable loopback API endpoint at `127.0.0.1:6443`. The node image is pinned by
digest so the cluster is reproducible.

`kubernetes/mcp/mcp-readonly.yaml` creates `insighthub-prod` and binds the
`mcp-readonly` ServiceAccount to a namespace `Role`. It permits only `get`,
`list`, and `watch` for selected workload and service resources. It cannot
read Secrets, access another namespace, access cluster-scoped resources, or
write/delete anything.

After activating the existing virtual environment, run:

```bash
bash scripts/setup-kind-mcp.sh
```

The script creates a temporary admin kubeconfig only while bootstrapping, then
deletes it. It writes the ServiceAccount-only kubeconfig to the local path
already referenced by `.codex/config.toml`:
`C:\\Users\\longn\\.kube\\mcp\\insighthub-mcp.yaml`. This credential is not
tracked and must not be copied into source control or evidence.

Verify the credential without printing it:

```bash
KUBECONFIG=/mnt/c/Users/longn/.kube/mcp/insighthub-mcp.yaml kubectl get pods -n insighthub-prod
KUBECONFIG=/mnt/c/Users/longn/.kube/mcp/insighthub-mcp.yaml kubectl get pods -n default
KUBECONFIG=/mnt/c/Users/longn/.kube/mcp/insighthub-mcp.yaml kubectl get secrets -n insighthub-prod
KUBECONFIG=/mnt/c/Users/longn/.kube/mcp/insighthub-mcp.yaml kubectl delete pod placeholder -n insighthub-prod --dry-run=server
```

Only the first command should succeed. The last three must return `Forbidden`.
