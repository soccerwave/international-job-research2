from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.state.r2_store import R2StateStore


def mb(value: int) -> float:
    return round(value / 1024 / 1024, 2)


def main() -> int:
    store = R2StateStore.from_env()
    client = store.client
    bucket = store.bucket

    token = None
    total_objects = 0
    total_bytes = 0
    by_top = defaultdict(lambda: [0, 0])
    by_second = defaultdict(lambda: [0, 0])
    largest = []

    while True:
        kwargs = {"Bucket": bucket}
        if token:
            kwargs["ContinuationToken"] = token
        response = client.list_objects_v2(**kwargs)
        for obj in response.get("Contents") or []:
            key = str(obj.get("Key") or "")
            size = int(obj.get("Size") or 0)
            total_objects += 1
            total_bytes += size

            parts = key.split("/")
            top = parts[0] if parts and parts[0] else "<root>"
            second = "/".join(parts[:2]) if len(parts) >= 2 else top
            by_top[top][0] += 1
            by_top[top][1] += size
            by_second[second][0] += 1
            by_second[second][1] += size
            largest.append((size, key))

        if not response.get("IsTruncated"):
            break
        token = str(response.get("NextContinuationToken") or "").strip() or None
        if token is None:
            raise RuntimeError("R2 inventory listing was truncated without a continuation token")

    largest.sort(reverse=True)

    payload = {
        "bucket": bucket,
        "total_objects": total_objects,
        "total_mb": mb(total_bytes),
        "top_level": [
            {"prefix": key, "objects": values[0], "mb": mb(values[1])}
            for key, values in sorted(by_top.items(), key=lambda item: item[1][1], reverse=True)
        ],
        "second_level": [
            {"prefix": key, "objects": values[0], "mb": mb(values[1])}
            for key, values in sorted(by_second.items(), key=lambda item: item[1][1], reverse=True)
        ],
        "largest_objects": [
            {"key": key, "mb": mb(size), "bytes": size}
            for size, key in largest[:25]
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
