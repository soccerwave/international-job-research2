"""Optional authenticated EURAXESS-only page fetch via an approved Worker.

No configuration means the existing direct collector path is unchanged.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse, urlencode, parse_qsl
import requests


class EuraxessWorkerSession:
    def __init__(self, endpoint: str, token: str):
        if not endpoint.startswith("https://"):
            raise ValueError("EURAXESS_WORKER_URL must use HTTPS")
        if not token:
            raise ValueError("EURAXESS_WORKER_TOKEN required")
        self.endpoint, self.token = endpoint, token
        self.transport = requests.Session()

    def request(self, method: str, url: str, **kwargs):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "euraxess.ec.europa.eu":
            raise ValueError("Worker transport limited to EURAXESS")
        if not (parsed.path == "/jobs/search" or
                (parsed.path.startswith("/jobs/") and parsed.path[6:].isdigit())):
            raise ValueError("Unexpected EURAXESS path")
        params = parse_qsl(parsed.query, keep_blank_values=True)
        params.extend(list(kwargs.pop("params", None) or []))
        if kwargs.get("data"):
            raise ValueError("Body POST is unsupported for Worker transport")
        response = self.transport.post(
            self.endpoint,
            json={"method":method.upper(), "path":parsed.path,
                  "query":urlencode(params, doseq=True)},
            headers={"Authorization":"Bearer "+self.token},
            timeout=kwargs.get("timeout", (10,45)),
            allow_redirects=False,
        )
        if response.status_code >= 400:
            upstream_url = response.headers.get("x-euraxess-final-url", "")
            origin = "euraxess_upstream" if upstream_url.startswith(
                "https://euraxess.ec.europa.eu/"
            ) else "worker_or_cloudflare"
            raise requests.HTTPError(
                f"EURAXESS transport HTTP {response.status_code}; "
                f"error_origin={origin}; "
                f"requested_path={parsed.path}; "
                f"upstream_path={urlparse(upstream_url).path if upstream_url else 'unknown'}",
                response=response,
            )
        # The Worker propagates upstream HTTP status in its response.
        result = requests.Response()
        result.status_code = response.status_code
        result._content = response.content
        result.encoding = response.encoding or "utf-8"
        result.url = response.headers.get("x-euraxess-final-url") or url
        result.headers = response.headers.copy()
        return result

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def configured_session():
    endpoint = os.getenv("EURAXESS_WORKER_URL", "").strip()
    token = os.getenv("EURAXESS_WORKER_TOKEN", "").strip()
    if not endpoint and not token:
        return None
    if not endpoint or not token:
        raise ValueError("Both EURAXESS_WORKER_URL and EURAXESS_WORKER_TOKEN are required")
    return EuraxessWorkerSession(endpoint, token)
