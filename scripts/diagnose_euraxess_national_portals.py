"""Read-only bounded EURAXESS national-domain availability diagnostic.

No Collector state writes or production changes. Designed to test 6 national
domains and the central portal with one HTTP GET each, no retries.
"""
import json
import re
from urllib.parse import urlparse
import requests

DOMAINS = [
    "euraxess.ec.europa.eu",
    "www.euraxess.de",
    "www.euraxess.es",
    "www.euraxess.se",
    "www.euraxess.dk",
    "www.euraxess.hr",
    "www.euraxess.ee",
]
PATTERN = re.compile(r'href=["\\\'](?:https?://[^/]+)?/jobs/(\\d+)', re.I)


def inspect(host):
    url = "https://" + host + "/jobs/search"
    try:
        r = requests.get(url, timeout=15, allow_redirects=True,
                         headers={"Accept": "text/html"})
        ids = list(dict.fromkeys(PATTERN.findall(r.text)))[:10] if r.status_code == 200 else []
        return {"domain":host, "status":r.status_code,
                "final_host":urlparse(r.url).hostname,
                "x_cache":r.headers.get("x-cache"),
                "server":r.headers.get("server"),
                "html_bytes":len(r.content) if r.status_code == 200 else 0,
                "job_ids":ids}
    except requests.RequestException as exc:
        return {"domain":host,"error":type(exc).__name__}


def main():
    results=[inspect(host) for host in DOMAINS]
    sets=[set(r.get("job_ids",[])) for r in results]
    central=sets[0]
    for r, ids in zip(results,sets):
        r["overlap_with_central"] = len(ids & central) if central else None
    print(json.dumps({"diagnostic":"euraxess_national_portal_access",
                      "sites":results},indent=2))
    # Discovery is informative even if the CDN denies every request.


if __name__=="__main__":
    main()
