"""Bounded, non-bypassing access diagnosis for EURAXESS from the Actions runner."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

URLS = (
    "https://euraxess.ec.europa.eu/",
    "https://euraxess.ec.europa.eu/jobs",
    "https://euraxess.ec.europa.eu/jobs/search",
)
SAFE_HEADERS = ("content-type", "retry-after", "server", "x-cache")


def main() -> None:
    results = []
    for url in URLS:
        request = urllib.request.Request(url, headers={"User-Agent": "international-job-research/euraxess-diagnostic"})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                results.append({
                    "path": urlparse(url).path,
                    "status": response.status,
                    "final_path": urlparse(response.url).path,
                    "headers": {key: response.headers.get(key) for key in SAFE_HEADERS if response.headers.get(key)},
                })
        except urllib.error.HTTPError as exc:
            results.append({
                "path": urlparse(url).path,
                "status": exc.code,
                "final_path": urlparse(exc.url).path,
                "headers": {key: exc.headers.get(key) for key in SAFE_HEADERS if exc.headers.get(key)},
            })
        except Exception as exc:
            results.append({"path": urlparse(url).path, "error_type": type(exc).__name__})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
