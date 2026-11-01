"""Read-only weekly audit export from the already published R2 reports.

No production changes, no AI requests, no R2 writes. Output: indexed Excel
and dated original Excel reports in one ZIP. Missing days are explicit.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from io import BytesIO
import json
import os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import boto3
import xlsxwriter

SOURCES = {
    "luna": ("llm/reports/runs/", "shadow_summary.json", "llm_shadow_report.xlsx"),
    "collector": ("control-plane/runs/", "report_summary.json", "international_academic_job_audit.xlsx"),
}
MAX_REPORT_BYTES = 25_000_000
MAX_TOTAL_BYTES = 160_000_000


def client_from_env():
    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("R2_ENDPOINT") or f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def list_keys(client, bucket, prefix):
    continuation = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        page = client.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            yield obj
        if not page.get("IsTruncated"):
            break
        continuation = page.get("NextContinuationToken")
        if not continuation:
            raise RuntimeError("R2 listing truncated without continuation token")


def read_json(client, bucket, key):
    obj = client.get_object(Bucket=bucket, Key=key)
    if int(obj.get("ContentLength") or 0) > 1_000_000:
        raise ValueError("Unexpectedly large manifest")
    return json.loads(obj["Body"].read().decode("utf-8"))


def get_bytes(client, bucket, key):
    head = client.head_object(Bucket=bucket, Key=key)
    size = int(head["ContentLength"])
    if size > MAX_REPORT_BYTES:
        raise ValueError(f"Report exceeds per-file limit: {key}")
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def day_of(manifest):
    # The production run ID's GitHub run timestamp is not the calendar date.
    # Published date is observable and explicitly used as the grouping date.
    return str(manifest.get("published_at") or "")[:10]


def excel_safe(v):
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False, sort_keys=True)
    if v is None:
        return ""
    if isinstance(v, str):
        if v.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + v
        return v[:32000]
    if isinstance(v, (int, float, bool)):
        return v
    return str(v)[:32000]


def export(start, end, output):
    bucket = os.environ["R2_BUCKET"]
    client = client_from_env()
    selected = []
    for family, (prefix, summary_name, report_name) in SOURCES.items():
        for obj in list_keys(client, bucket, prefix):
            key = obj["Key"]
            if not key.endswith("/" + summary_name):
                continue
            # Run-scoped R2 reports have no per-run manifest.json.
            # Use object publication date and exact sibling keys, not latest pointers.
            modified = obj.get("LastModified")
            day = modified.date().isoformat() if modified else ""
            if not (start <= day <= end):
                continue
            base = key.rsplit("/", 1)[0]
            run_name = base.rsplit("/", 1)[-1]
            manifest = {
                "summary_key": key,
                "report_key": base + "/" + report_name,
                "audit_report_key": base + "/international_academic_job_audit.xlsx" if family == "collector" else None,
                "published_at": modified.isoformat() if modified else "",
                "github_run_id": run_name,
            }
            selected.append((family, day, key, manifest))
    # Prefer latest publication of each source type on each date, but
    # preserve all manifest rows for provenance / reruns.
    selected.sort(key=lambda x: (x[0], x[1], x[3].get("published_at", "")))
    by_day = {}
    for family, day, key, manifest in selected:
        by_day[family, day] = (family, day, key, manifest)
    chosen = sorted(by_day.values(), key=lambda x: (x[1], x[0]))
    day_list = [(start_date + timedelta(days=i)).isoformat()
                for start_date in [date.fromisoformat(start)]
                for i in range((date.fromisoformat(end)-start_date).days+1)]
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_rows, inventory_rows, missing_rows = [], [], []
    total_bytes = 0
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for day in day_list:
            for family in SOURCES:
                if (family, day) not in by_day:
                    missing_rows.append([day, family, "NO_PUBLISHED_SUMMARY"])
        for family, day, manifest_key, manifest in chosen:
            summary_key = manifest.get("summary_key")
            report_key = manifest.get("report_key")
            if family == "collector":
                audit_key = manifest.get("audit_report_key")
                try:
                    client.head_object(Bucket=bucket, Key=audit_key)
                    report_key = audit_key
                except client.exceptions.ClientError as exc:
                    if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
                        raise
            record = {"date": day, "family": family, "production_run_id": manifest.get("production_run_id"),
                      "github_run_id": manifest.get("github_run_id"), "published_at": manifest.get("published_at"),
                      "manifest_key": manifest_key, "summary_key": summary_key, "report_key": report_key}
            if summary_key:
                try:
                    payload = read_json(client, bucket, summary_key)
                    archive.writestr(f"daily/{day}/{family}_summary.json",
                                     json.dumps(payload, ensure_ascii=False, indent=2))
                    # Flatten scalar summary metrics, retain nested summary sections as JSON.
                    for k, v in payload.items():
                        summary_rows.append([day, family, str(k), excel_safe(v), str(summary_key)])
                except Exception as exc:
                    missing_rows.append([day, family, "SUMMARY_ERROR:" + type(exc).__name__])
            else:
                missing_rows.append([day, family, "NO_SUMMARY_KEY"])
            if report_key:
                try:
                    data = get_bytes(client, bucket, report_key)
                    if not data.startswith(b"PK"):
                        raise ValueError("Report is not an Excel file")
                    total_bytes += len(data)
                    if total_bytes > MAX_TOTAL_BYTES:
                        raise ValueError("Weekly report download limit reached")
                    archive.writestr(f"daily/{day}/{family}_report.xlsx", data)
                    record["excel_bytes"] = len(data)
                except Exception as exc:
                    missing_rows.append([day, family, "REPORT_ERROR:" + type(exc).__name__])
            else:
                missing_rows.append([day, family, "NO_REPORT_KEY"])
            inventory_rows.append(record)
        index = BytesIO()
        workbook = xlsxwriter.Workbook(index, {"in_memory": True})
        header = workbook.add_format({"bold":True,"bg_color":"#183153","font_color":"#FFFFFF"})
        hint = workbook.add_format({"text_wrap":True,"valign":"top"})
        for title, heads, rows in [
            ("README", ["topic","description"], [
                ["date_range", f"{start} to {end} (R2 object modified date, UTC)"],
                ["method", "R2 read-only; reuse published reports; no evaluator rerun"],
                ["luna", "Published shadow summary and original XLSX; not a ground-truth recall estimate"],
                ["collector", "Prefer control-plane audit XLSX when published; otherwise use clean XLSX; not raw shard artifacts"],
                ["coverage", "Missing_Days lists unavailable publications and download errors"],
                ["selection", "Latest run-scoped summary object per source per R2 LastModified UTC day"],
                ["caution", "Rule-vs-Luna false negatives require raw paired labels and human validation"]
            ]),
            ("Manifest_Index", ["date","family","production_run_id","github_run_id","published_at","manifest_key","summary_key","report_key","excel_bytes"],
             [[r.get(k,"") for k in ["date","family","production_run_id","github_run_id","published_at","manifest_key","summary_key","report_key","excel_bytes"]] for r in inventory_rows]),
            ("Metrics", ["date","family","metric","value","source_key"], summary_rows),
            ("Missing_Days", ["date","family","reason"], missing_rows),
        ]:
            ws = workbook.add_worksheet(title)
            ws.freeze_panes(1, 0)
            ws.write_row(0, 0, heads, header)
            for idx, row in enumerate(rows,1):
                for col, val in enumerate(row):
                    ws.write(idx, col, excel_safe(val), hint if title=="README" else None)
            ws.set_column(0, 0, 18)
            ws.set_column(1, 1, 24)
            ws.set_column(2, len(heads)-1, 42)
            ws.autofilter(0,0,max(len(rows),1),len(heads)-1)
        workbook.close()
        archive.writestr("weekly_audit_index.xlsx",index.getvalue())
        archive.writestr("export_manifest.json",json.dumps({
            "date_start":start,"date_end":end,"published_report_pairs":len(chosen),
            "missing":missing_rows,"total_excel_bytes":total_bytes
        },indent=2))
    print(json.dumps({"output":str(output),"report_pairs":len(chosen),
                      "missing":len(missing_rows),"report_bytes":total_bytes}))
    if not chosen:
        raise RuntimeError("No published R2 run-scoped summaries found for selected dates")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--start",required=True)
    parser.add_argument("--end",required=True)
    parser.add_argument("--out",type=Path,default=Path("weekly-audit-export.zip"))
    args=parser.parse_args()
    if date.fromisoformat(args.end)<date.fromisoformat(args.start):
        parser.error("end before start")
    if (date.fromisoformat(args.end)-date.fromisoformat(args.start)).days>13:
        parser.error("Maximum window is 14 days")
    export(args.start,args.end,args.out)
