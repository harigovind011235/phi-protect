import time

import httpx

HEALTH_TIMEOUT_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 90
POLL_INTERVAL_SECONDS = 0.5


class ServiceError(Exception):
    """The service could not answer. The message is safe to show: it never contains content."""


class ServiceClient:
    """Talks to the PHI Protect service over HTTP. Used by the hook and the CLI commands."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def is_running(self) -> bool:
        try:
            response = httpx.get(f"{self._base_url}/health", timeout=HEALTH_TIMEOUT_SECONDS)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def wait_until_running(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.is_running():
                return True
            time.sleep(POLL_INTERVAL_SECONDS)
        return self.is_running()

    def scan_text(self, text: str) -> dict:
        return self._post("/scan", json={"text": text}).json()

    def scan_file(self, data: bytes) -> dict:
        # The real file name is never sent: file names can contain patient names too.
        return self._post("/scan-file", files={"file": ("file", data)}).json()

    def deidentify_file(self, data: bytes) -> tuple[bytes, str]:
        response = self._post("/deidentify-file", files={"file": ("file", data)})
        return response.content, response.headers.get("content-type", "")

    def _post(self, path: str, **kwargs) -> httpx.Response:
        try:
            response = httpx.post(
                f"{self._base_url}{path}", timeout=REQUEST_TIMEOUT_SECONDS, **kwargs
            )
        except httpx.TimeoutException as error:
            raise ServiceError("the service took too long to answer") from error
        except httpx.HTTPError as error:
            raise ServiceError("the service is not reachable") from error
        if response.status_code == 422:
            raise ServiceError(response.json().get("reason") or "the input could not be checked")
        if response.status_code != 200:
            raise ServiceError(f"the service answered with HTTP {response.status_code}")
        return response
