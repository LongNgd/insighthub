"""The sole mutation adapter, deliberately separate from read-only MCP calls."""

from urllib.parse import quote

import httpx

from app.config import Settings, get_settings
from app.errors import (
    MutationExecutorUnavailable,
    MutationOutcomeUnknown,
    PermanentProcessingError,
)
from app.policy import ActionRequest


class KubernetesScaleExecutor:
    """Patch only the deployment scale subresource with a dedicated identity."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def execute(self, request: ActionRequest) -> None:
        """Perform one bounded PATCH; ambiguous transport failures are never retried."""

        if request.action != "scale_deployment" or not self._ready():
            raise MutationExecutorUnavailable()
        namespace, deployment = request.target.split("/", 1)
        url = (
            f"{self._settings.write_kubernetes_api_url}/apis/apps/v1/namespaces/"
            f"{quote(namespace, safe='')}/deployments/{quote(deployment, safe='')}/scale"
        )
        headers = {
            "Authorization": f"Bearer {self._settings.write_kubernetes_bearer_token}",
            "Content-Type": "application/merge-patch+json",
            "Accept": "application/json",
        }
        payload = {"spec": {"replicas": request.arguments["replicas"]}}
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.patch(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise MutationOutcomeUnknown() from error
        if 200 <= response.status_code < 300:
            return
        if response.status_code in {400, 401, 403, 404, 409, 422}:
            raise PermanentProcessingError()
        # A gateway/server error cannot prove that the API did not receive PATCH.
        raise MutationOutcomeUnknown()

    def _ready(self) -> bool:
        """Fail closed unless the independent writer identity is fully configured."""

        return bool(
            self._settings.write_enabled
            and self._settings.write_kubernetes_api_url.startswith("https://")
            and self._settings.write_kubernetes_bearer_token
        )
