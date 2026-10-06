from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


UI_BOILERPLATE_LINES = {
    "skip to main content",
    "skip to content",
    "back to search results",
    "back to jobs",
    "print this page",
    "share this job",
    "cookie settings",
    "accept all cookies",
    "reject all cookies",
    "manage cookies",
    "apply now",
    "save job",
}

SECTION_ALIASES = {
    "responsibilities": {
        "responsibilities",
        "key responsibilities",
        "main responsibilities",
        "duties",
        "key duties",
        "role responsibilities",
        "what you will do",
        "what you'll do",
        "the role",
    },
    "essential": {
        "essential criteria",
        "essential requirements",
        "required qualifications",
        "required qualifications and experience",
        "minimum qualifications",
        "minimum requirements",
        "requirements",
        "what you need",
        "about you",
    },
    "desirable": {
        "desirable criteria",
        "desirable requirements",
        "preferred qualifications",
        "preferred requirements",
        "nice to have",
        "advantageous",
    },
}

_HEADING_NORMALIZER = re.compile(r"[^a-z0-9']+")


@dataclass(frozen=True)
class ContextQualityResult:
    full_text: str
    responsibilities_text: str | None
    essential_criteria_text: str | None
    desirable_criteria_text: str | None
    original_chars: int
    cleaned_chars: int
    final_chars: int
    boilerplate_lines_removed: int
    duplicate_blocks_removed: int
    truncated: bool
    truncation_strategy: str | None


def _normalize_heading(text: str) -> str:
    normalized = _HEADING_NORMALIZER.sub(" ", text.lower()).strip()
    return " ".join(normalized.split())


def _is_heading(line: str) -> tuple[str, str] | None:
    stripped = line.strip().strip(":").strip()
    if not stripped or len(stripped) > 90:
        return None
    normalized = _normalize_heading(stripped)
    for section, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return section, stripped
    return None


def _clean_lines(text: str) -> tuple[list[str], int]:
    removed = 0
    cleaned: list[str] = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(raw.split()).strip()
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if line.lower().strip(" :") in UI_BOILERPLATE_LINES:
            removed += 1
            continue
        cleaned.append(line)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned, removed


def _paragraphs(lines: Iterable[str]) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line == "":
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        if _is_heading(line) and current:
            paragraphs.append("\n".join(current).strip())
            current = [line]
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    return [p for p in paragraphs if p]


def _dedupe_exact_blocks(blocks: Iterable[str]) -> tuple[list[str], int]:
    seen: set[str] = set()
    output: list[str] = []
    removed = 0
    for block in blocks:
        key = re.sub(r"\s+", " ", block).strip().casefold()
        if len(key) >= 24 and key in seen:
            removed += 1
            continue
        if len(key) >= 24:
            seen.add(key)
        output.append(block.strip())
    return output, removed


def clean_vacancy_text(text: str) -> tuple[str, int, int]:
    lines, boilerplate_removed = _clean_lines(text)
    blocks, duplicates_removed = _dedupe_exact_blocks(_paragraphs(lines))
    return "\n\n".join(blocks).strip(), boilerplate_removed, duplicates_removed


def extract_sections(cleaned_text: str) -> dict[str, str | None]:
    lines = cleaned_text.splitlines()
    buckets: dict[str, list[str]] = {"responsibilities": [], "essential": [], "desirable": []}
    current: str | None = None
    for line in lines:
        heading = _is_heading(line)
        if heading:
            current = heading[0]
            continue
        if current is not None:
            buckets[current].append(line)

    result: dict[str, str | None] = {}
    for section, values in buckets.items():
        text = "\n".join(values).strip()
        result[section] = text or None
    return result


def _append_unique(parts: list[str], text: str | None) -> None:
    if not text:
        return
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    if not normalized:
        return
    for existing in parts:
        if normalized == re.sub(r"\s+", " ", existing).strip().casefold():
            return
    parts.append(text.strip())


def _truncate_preserving_sections(
    cleaned_text: str,
    *,
    max_chars: int,
    responsibilities: str | None,
    essential: str | None,
    desirable: str | None,
) -> str:
    if len(cleaned_text) <= max_chars:
        return cleaned_text
    if max_chars < 4000:
        raise ValueError("max_chars must be at least 4000 when truncation is enabled")

    protected: list[str] = []
    _append_unique(protected, essential)
    _append_unique(protected, desirable)
    _append_unique(protected, responsibilities)

    protected_text = "\n\n".join(protected).strip()
    if protected_text and len(protected_text) >= max_chars:
        # Do not keyword-summarize or selectively drop requirements. If the protected
        # source sections alone exceed the budget, retain them verbatim and allow the
        # context to exceed the requested soft budget rather than silently losing them.
        return protected_text

    marker = "\n\n[... middle source text omitted because context budget was exceeded ...]\n\n"
    remaining = max_chars - len(protected_text) - len(marker)
    if protected_text:
        remaining -= 2
    remaining = max(0, remaining)

    head_budget = remaining // 2
    tail_budget = remaining - head_budget
    head = cleaned_text[:head_budget].rstrip()
    tail = cleaned_text[-tail_budget:].lstrip() if tail_budget else ""

    parts: list[str] = []
    if head:
        parts.append(head)
    if protected_text:
        parts.append(protected_text)
    if tail:
        parts.append(tail)
    return marker.join(parts).strip()


def prepare_vacancy_context(text: str, *, max_chars: int | None = None) -> ContextQualityResult:
    original = text or ""
    cleaned, boilerplate_removed, duplicates_removed = clean_vacancy_text(original)
    sections = extract_sections(cleaned)

    final_text = cleaned
    truncated = False
    strategy: str | None = None
    if max_chars is not None and len(cleaned) > max_chars:
        final_text = _truncate_preserving_sections(
            cleaned,
            max_chars=max_chars,
            responsibilities=sections["responsibilities"],
            essential=sections["essential"],
            desirable=sections["desirable"],
        )
        truncated = final_text != cleaned
        strategy = "SECTION_PRESERVING_HEAD_TAIL" if truncated else None

    return ContextQualityResult(
        full_text=final_text,
        responsibilities_text=sections["responsibilities"],
        essential_criteria_text=sections["essential"],
        desirable_criteria_text=sections["desirable"],
        original_chars=len(original),
        cleaned_chars=len(cleaned),
        final_chars=len(final_text),
        boilerplate_lines_removed=boilerplate_removed,
        duplicate_blocks_removed=duplicates_removed,
        truncated=truncated,
        truncation_strategy=strategy,
    )
