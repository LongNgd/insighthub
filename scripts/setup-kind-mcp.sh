#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
kind_config="${project_root}/kubernetes/kind/insighthub.yaml"
rbac_manifest="${project_root}/kubernetes/mcp/mcp-readonly.yaml"
kind_admin_kubeconfig="$(mktemp)"
windows_user_profile="$(powershell.exe -NoProfile -Command '[Environment]::GetFolderPath("UserProfile")' | tr -d '\r')"
mcp_kubeconfig="$(wslpath "${windows_user_profile}")/.kube/mcp/insighthub-mcp.yaml"
mcp_kubeconfig_dir="$(dirname "${mcp_kubeconfig}")"
mcp_kubeconfig_tmp=""
cluster_ca_file=""
token_wait_attempts=30

cleanup() {
  rm -f "${kind_admin_kubeconfig}" "${cluster_ca_file}" "${mcp_kubeconfig_tmp}"
}
trap cleanup EXIT

if ! command -v kind >/dev/null 2>&1; then
  printf 'kind must be installed and available after activating .venv.\n' >&2
  exit 1
fi

if kind get clusters | grep -Fxq 'insighthub'; then
  printf 'Using existing kind cluster "insighthub".\n'
  kind export kubeconfig \
    --name insighthub \
    --kubeconfig "${kind_admin_kubeconfig}"
else
  kind create cluster \
    --name insighthub \
    --config "${kind_config}" \
    --kubeconfig "${kind_admin_kubeconfig}"
fi

kubectl --kubeconfig "${kind_admin_kubeconfig}" apply -f "${rbac_manifest}"

for ((attempt = 1; attempt <= token_wait_attempts; attempt++)); do
  token_value="$(kubectl --kubeconfig "${kind_admin_kubeconfig}" -n insighthub-prod get secret mcp-readonly-token -o jsonpath='{.data.token}' 2>/dev/null || true)"
  if [[ -n "${token_value}" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "${token_value:-}" ]]; then
  printf 'Timed out waiting for the mcp-readonly token Secret.\n' >&2
  exit 1
fi

cluster_server="$(kubectl --kubeconfig "${kind_admin_kubeconfig}" config view --raw --minify -o jsonpath='{.clusters[0].cluster.server}')"
cluster_ca_file="$(mktemp)"
kubectl --kubeconfig "${kind_admin_kubeconfig}" config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 --decode > "${cluster_ca_file}"

mkdir -p "${mcp_kubeconfig_dir}"
umask 077
mcp_kubeconfig_tmp="$(mktemp "${mcp_kubeconfig_dir}/insighthub-mcp.yaml.XXXXXX")"
kubectl config --kubeconfig "${mcp_kubeconfig_tmp}" set-cluster insighthub \
  --server="${cluster_server}" \
  --certificate-authority="${cluster_ca_file}" \
  --embed-certs=true
kubectl config --kubeconfig "${mcp_kubeconfig_tmp}" set-credentials mcp-readonly --token="$(printf '%s' "${token_value}" | base64 --decode)"
kubectl config --kubeconfig "${mcp_kubeconfig_tmp}" set-context insighthub-prod-readonly \
  --cluster=insighthub \
  --user=mcp-readonly \
  --namespace=insighthub-prod
kubectl config --kubeconfig "${mcp_kubeconfig_tmp}" use-context insighthub-prod-readonly
chmod 600 "${mcp_kubeconfig_tmp}"
mv -f "${mcp_kubeconfig_tmp}" "${mcp_kubeconfig}"
mcp_kubeconfig_tmp=""

printf 'Created local MCP kubeconfig at %s\n' "${mcp_kubeconfig}"
