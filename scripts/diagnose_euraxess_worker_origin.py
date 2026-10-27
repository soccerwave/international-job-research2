"""Bounded, authenticated diagnostic. No state writes and no secrets logged."""
import json
import os
import requests

endpoint = os.environ["EURAXESS_WORKER_URL"].strip()
token = os.environ["EURAXESS_WORKER_TOKEN"].strip()
if not endpoint.startswith("https://") or not token:
    raise SystemExit("Missing HTTPS Worker endpoint or secret")
response = requests.post(
    endpoint,
    json={"mode": "diagnose"},
    headers={"Authorization": "Bearer " + token},
    timeout=45,
)
print("worker_http_status:", response.status_code)
try:
    data = response.json()
except ValueError:
    print("worker_response_is_not_json")
    raise SystemExit(1)
if response.status_code != 200 or data.get("experiment") != "euraxess_worker_fetch_comparison":
    print("diagnostic_unavailable:", str(data)[:250])
    raise SystemExit(1)
print(json.dumps(data, sort_keys=True))
