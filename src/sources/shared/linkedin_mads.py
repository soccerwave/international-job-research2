from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .pagination import paginate, reached, record_coverage
from .common import CODE_TO_COUNTRY_NAME, clean, make_record

SOURCE_KEY="linkedin_mads"
PROVIDER="LinkedIn via MadsLorentzen/ai-job-search"
CLI_RELATIVE=Path(".agents/skills/linkedin-search/cli/src/cli.ts")
MADS_PIN="fd89eac178dc546d41f6c1a3213de88d96112c6d"
EUROPE_LOCATIONS=("Netherlands","Germany","Ireland","United Kingdom","Belgium","France","Austria")
AUSTRALIA_LOCATIONS=("Australia",)
DEFAULT_QUERIES=("postdoctoral researcher","research fellow","assistant professor","lecturer")
Runner=Callable[[Path,list[str]],subprocess.CompletedProcess[str]]

_LOG_LOCK=threading.Lock()
_CHECKPOINT_LOCK=threading.Lock()
HEARTBEAT_SECONDS=30
CHECKPOINT_VERSION=1


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _progress(event: str, **fields: Any) -> None:
    """Emit flushed diagnostics without JD bodies, credentials, or environment dumps."""
    entry=dict(timestamp=_utcnow(),event=event,**fields)
    line=json.dumps(entry,ensure_ascii=False)
    with _LOG_LOCK:
        print("[linkedin] "+line,file=sys.stderr,flush=True)
        path=os.getenv("LINKEDIN_PROGRESS_PATH")
        if path:
            target=Path(path)
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("a",encoding="utf-8") as handle:
                handle.write(line+"\n")
                handle.flush()


def _checkpoint_root() -> Path | None:
    raw=clean(os.getenv("LINKEDIN_CHECKPOINT_DIR"))
    return Path(raw) if raw else None


def _append_checkpoint(filename: str, event: str, **fields: Any) -> None:
    """Append durable job data after completed units of LinkedIn work."""
    root=_checkpoint_root()
    if root is None:
        return
    entry=dict(checkpoint_version=CHECKPOINT_VERSION,timestamp=_utcnow(),event=event,**fields)
    line=json.dumps(entry,ensure_ascii=False,default=str)
    with _CHECKPOINT_LOCK:
        root.mkdir(parents=True,exist_ok=True)
        with (root/filename).open("a",encoding="utf-8") as handle:
            handle.write(line+"\n")
            handle.flush()


def _write_checkpoint_state(**fields: Any) -> None:
    """Atomically expose the latest checkpoint position without changing resume semantics."""
    root=_checkpoint_root()
    if root is None:
        return
    state=dict(checkpoint_version=CHECKPOINT_VERSION,updated_at=_utcnow(),**fields)
    with _CHECKPOINT_LOCK:
        root.mkdir(parents=True,exist_ok=True)
        target=root/"state.json"
        temporary=root/"state.json.tmp"
        temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
        temporary.replace(target)


@contextmanager
def _operation(stage: str, **fields: Any):
    started=time.monotonic()
    done=threading.Event()
    _progress("request_start",stage=stage,**fields)

    def heartbeat() -> None:
        while not done.wait(HEARTBEAT_SECONDS):
            _progress(
                "request_waiting",
                stage=stage,
                elapsed_seconds=round(time.monotonic()-started,2),
                **fields,
            )

    thread=threading.Thread(target=heartbeat,daemon=True)
    thread.start()
    try:
        yield
    except Exception as exc:
        _progress(
            "request_error",
            stage=stage,
            error_type=type(exc).__name__,
            error=clean(str(exc))[:1000],
            elapsed_seconds=round(time.monotonic()-started,2),
            **fields,
        )
        raise
    else:
        _progress(
            "request_done",
            stage=stage,
            elapsed_seconds=round(time.monotonic()-started,2),
            **fields,
        )
    finally:
        done.set()
        thread.join()


def resolve_repo(explicit: str|Path|None=None)->Path:
    candidates=[]
    if explicit: candidates.append(Path(explicit).expanduser())
    if os.getenv("AI_JOB_SEARCH_MADS_REPO"): candidates.append(Path(os.environ["AI_JOB_SEARCH_MADS_REPO"]).expanduser())
    candidates += [Path.cwd()/".vendor"/"ai-job-search",Path.home()/"ai-job-search"]
    for repo in candidates:
        if (repo/CLI_RELATIVE).exists():
            return repo
    raise FileNotFoundError("Mads ai-job-search repository with linkedin-search CLI not found")


def _default_runner(repo:Path,args:list[str])->subprocess.CompletedProcess[str]:
    if not shutil.which("bun"):
        raise RuntimeError("bun is not available in PATH")
    return subprocess.run(["bun","run",*args],cwd=repo,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180)


def _json(repo:Path,args:list[str],runner:Runner|None=None)->dict[str,Any]:
    p=(runner or _default_runner)(repo,args)
    if p.returncode!=0:
        raise RuntimeError(clean(p.stderr) or clean(p.stdout) or "LinkedIn CLI failed")
    raw=(p.stdout or "").strip()
    if not raw: return {"results":[]}
    obj=json.loads(raw)
    return {"results":obj} if isinstance(obj,list) else obj


def _plain(repo:Path,args:list[str],runner:Runner|None=None)->str:
    p=(runner or _default_runner)(repo,args)
    if p.returncode!=0:
        raise RuntimeError(clean(p.stderr) or clean(p.stdout) or "LinkedIn detail CLI failed")
    return (p.stdout or "").strip()


def collect(
    *, locations:tuple[str,...]=EUROPE_LOCATIONS, queries:tuple[str,...]=DEFAULT_QUERIES,
    limit_per_search:int | None=5, jobage_days:int=7, max_jobs:int | None=100, enrich_detail:bool=True,
    repo_path:str|Path|None=None, runner:Runner|None=None,
)->list[dict[str,Any]]:
    repo=resolve_repo(repo_path)
    started=time.monotonic()
    _progress(
        "collection_start",
        locations=list(locations),queries=list(queries),max_jobs=max_jobs,
        limit_per_search=limit_per_search,jobage_days=jobage_days,
        enrich_detail=enrich_detail,request_timeout_seconds=180,
    )
    _write_checkpoint_state(
        stage="discovery",status="RUNNING",locations=list(locations),queries=list(queries),
        completed_pages=0,unique_discovered=0,completed_records=0,
    )
    found={}; order=[]
    page_count=0
    search_failures=0
    detail_failures=0

    for location in locations:
        for query in queries:
            query_started=time.monotonic()
            query_seen=set()

            def fetch(page):
                nonlocal page_count
                args=[str(CLI_RELATIVE),"search","-q",query,"-l",location,
                      "--page",str(page),"--jobage",str(jobage_days),"--format","json"]
                if limit_per_search is not None:
                    args.extend(["--limit",str(limit_per_search)])
                with _operation("search",country=location,query=query,page=page):
                    payload=_json(repo,args,runner)
                page_count+=1
                items=[]
                for item in payload.get("results",[]):
                    if not isinstance(item,dict): continue
                    jid=clean(item.get("id")) or clean(item.get("url"))
                    if jid and clean(item.get("title")):
                        items.append(dict(item,id=jid))
                new_ids={item["id"] for item in items}-query_seen
                query_seen.update(new_ids)
                _append_checkpoint(
                    "discovery.jsonl","search_page",
                    country=location,query=query,page=page,items=items,
                )
                _write_checkpoint_state(
                    stage="discovery",status="RUNNING",country=location,query=query,page=page,
                    completed_pages=page_count,query_unique=len(query_seen),
                    unique_discovered=len(order),completed_records=0,
                )
                _progress(
                    "page_result",country=location,query=query,page=page,
                    returned=len(items),new_in_query=len(new_ids),
                    query_unique=len(query_seen),completed_pages=page_count,
                )
                return items,None,None

            try:
                batch=paginate(
                    fetch,source=f"{SOURCE_KEY}:{location}:{query}",
                    max_jobs=max_jobs,max_pages=1 if limit_per_search is not None else None,start=1,
                )
            except Exception as exc:
                search_failures+=1
                _progress(
                    "query_error",country=location,query=query,
                    error_type=type(exc).__name__,error=clean(str(exc))[:1000],
                    search_failures=search_failures,
                    elapsed_seconds=round(time.monotonic()-query_started,2),
                )
                continue

            for item in batch:
                if not isinstance(item,dict): continue
                jid=clean(item.get("id")) or clean(item.get("url"))
                if not jid or not clean(item.get("title")): continue
                if jid not in found:
                    found[jid]={"item":item,"queries":[query],"locations":[location]}; order.append(jid)
                else:
                    if query not in found[jid]["queries"]: found[jid]["queries"].append(query)
                    if location not in found[jid]["locations"]: found[jid]["locations"].append(location)
                if reached(order,max_jobs): break

            _write_checkpoint_state(
                stage="discovery",status="RUNNING",country=location,query=query,
                completed_pages=page_count,query_unique=len(query_seen),
                unique_discovered=len(order),completed_records=0,
            )
            _progress(
                "query_done",country=location,query=query,
                query_unique=len(query_seen),global_unique=len(order),
                elapsed_seconds=round(time.monotonic()-query_started,2),
            )
            if reached(order,max_jobs): break
        if reached(order,max_jobs): break

    if reached(order,max_jobs):
        record_coverage(SOURCE_KEY,"configured_record_limit")

    discovery_seconds=time.monotonic()-started
    _write_checkpoint_state(
        stage="detail" if enrich_detail else "complete",status="RUNNING" if enrich_detail else "COMPLETE",
        completed_pages=page_count,unique_discovered=len(order),completed_records=0,
        search_failures=search_failures,
    )
    _progress(
        "discovery_done",unique_discovered=len(order),completed_pages=page_count,
        search_failures=search_failures,elapsed_seconds=round(discovery_seconds,2),
    )

    out=[]
    detail_ids=order[:max_jobs]
    for index,jid in enumerate(detail_ids,1):
        meta=found[jid]; item=meta["item"]; detail=None; status="NOT_ATTEMPTED"; failure=None
        if enrich_detail:
            try:
                with _operation("detail",job_id=jid,index=index,total=len(detail_ids)):
                    detail=_plain(repo,[str(CLI_RELATIVE),"detail",str(jid),"--format","plain"],runner)
                status="FULL" if len(detail)>=200 else ("PARTIAL" if detail else "UNAVAILABLE")
            except Exception as exc:
                status="FETCH_FAILED"; failure=f"{type(exc).__name__}: {exc}"
                detail_failures+=1
            _progress(
                "detail_result",job_id=jid,index=index,total=len(detail_ids),
                status=status,characters=len(detail or ""),failures=detail_failures,
            )
        loc=clean(item.get("location")); code=None
        for c,name in CODE_TO_COUNTRY_NAME.items():
            if name.lower() in loc.lower() or any(name.lower()==x.lower() for x in meta["locations"]):
                code=c; break
        record=make_record(source_key=SOURCE_KEY,source_kind="LINKEDIN",provider=PROVIDER,
          source_job_id=str(jid),listing_url=clean(item.get("url")) or "https://www.linkedin.com/jobs/",
          detail_url=clean(item.get("url")) or None,title=clean(item.get("title")),institution=clean(item.get("company")) or None,
          country_code=code,country_name=CODE_TO_COUNTRY_NAME.get(code),city=loc or None,posted_text=clean(item.get("date")) or None,
          full_jd=detail,detail_status=status,detail_failure_reason=failure,source_language="en",
          source_status="OPEN" if status in {"FULL","PARTIAL"} else "UNKNOWN",
          raw_extra={"queries":meta["queries"],"search_locations":meta["locations"],"modality":item.get("modality"),"mads_commit":MADS_PIN})
        out.append(record)
        _append_checkpoint("records.jsonl","record",index=index,total=len(detail_ids),record=record)
        _write_checkpoint_state(
            stage="detail" if index < len(detail_ids) else "complete",
            status="RUNNING" if index < len(detail_ids) else "COMPLETE",
            completed_pages=page_count,unique_discovered=len(order),completed_records=len(out),
            total_records=len(detail_ids),search_failures=search_failures,detail_failures=detail_failures,
            last_job_id=str(jid),
        )

    total_seconds=time.monotonic()-started
    if not detail_ids:
        _write_checkpoint_state(
            stage="complete",status="COMPLETE",completed_pages=page_count,
            unique_discovered=len(order),completed_records=0,total_records=0,
            search_failures=search_failures,detail_failures=detail_failures,
        )
    _progress(
        "collection_done",records=len(out),search_failures=search_failures,
        detail_failures=detail_failures,discovery_seconds=round(discovery_seconds,2),
        detail_seconds=round(total_seconds-discovery_seconds,2),elapsed_seconds=round(total_seconds,2),
    )
    return out


def collect_europe()->list[dict[str,Any]]:
    return collect(locations=EUROPE_LOCATIONS)


def collect_australia()->list[dict[str,Any]]:
    return collect(locations=AUSTRALIA_LOCATIONS)
