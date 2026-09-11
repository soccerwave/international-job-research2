from __future__ import annotations

import json
import os

import boto3

PREFIX = "stage7/reference/v1/"
OBJECTS = (
    PREFIX + "reference_observations_v1.jsonl.enc",
    PREFIX + "reference_capture_log_v1.jsonl.enc",
)


def build_client():
    account_id = str(os.getenv("R2_ACCOUNT_ID") or "").strip()
    endpoint = str(os.getenv("R2_ENDPOINT") or "").strip() or (
        f"https://{account_id}.r2.cloudflarestorage.com" if account_id else ""
    )
    access_key = str(os.getenv("R2_ACCESS_KEY_ID") or "").strip()
    secret_key = str(os.getenv("R2_SECRET_ACCESS_KEY") or "").strip()
    missing = [
        name for name, value in {
            "R2_ACCOUNT_ID": account_id,
            "R2_ENDPOINT": endpoint,
            "R2_ACCESS_KEY_ID": access_key,
            "R2_SECRET_ACCESS_KEY": secret_key,
        }.items() if not value
    ]
    if missing:
        raise SystemExit("Missing R2 configuration: " + ", ".join(missing))
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def main() -> int:
    bucket = str(os.getenv("R2_BUCKET") or "").strip()
    if not bucket:
        raise SystemExit("R2_BUCKET is required")
    client = build_client()
    listed = client.list_objects_v2(Bucket=bucket, Prefix=PREFIX)
    present = {
        item["Key"]: {
            "size": int(item.get("Size") or 0),
            "last_modified": item["LastModified"].isoformat() if item.get("LastModified") else None,
            "etag": str(item.get("ETag") or "").strip('"'),
        }
        for item in listed.get("Contents", [])
    }
    result = {
        "bucket": bucket,
        "prefix": PREFIX,
        "expected_objects": {},
        "unexpected_object_count": len([key for key in present if key not in OBJECTS]),
    }
    for key in OBJECTS:
        info = present.get(key)
        result["expected_objects"][key] = {
            "exists": info is not None,
            **(info or {}),
        }
    result["all_expected_objects_exist"] = all(
        result["expected_objects"][key]["exists"] for key in OBJECTS
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
