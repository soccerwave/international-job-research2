from __future__ import annotations

from . import academicpositions, dvs, ecss, euraxess, fens, jobs_ac_uk, linkedin_mads

COLLECTORS = {
    "euraxess": euraxess.collect,
    "academicpositions": academicpositions.collect,
    "linkedin_europe": linkedin_mads.collect_europe,
    "linkedin_australia": linkedin_mads.collect_australia,
    "jobs_ac_uk": jobs_ac_uk.collect,
    "ecss": ecss.collect,
    "dvs": dvs.collect,
    "fens": fens.collect,
}

def get_collector(source_id: str):
    try:
        return COLLECTORS[source_id]
    except KeyError as exc:
        raise KeyError(f"unknown shared source: {source_id}") from exc
