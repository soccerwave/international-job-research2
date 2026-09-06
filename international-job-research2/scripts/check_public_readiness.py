from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

FORBIDDEN_SUFFIXES = {'.csv', '.xlsx', '.xls', '.pem', '.key', '.p12', '.pfx'}
FORBIDDEN_NAMES = {'.env'}
SECRET_PATTERNS = {
    'private_key': re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    'github_token': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b'),
    'aws_access_key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'telegram_bot_token': re.compile(r'\b\d{8,12}:[A-Za-z0-9_-]{30,}\b'),
}


def _git(*args: str) -> str:
    return subprocess.check_output(['git', *args], text=True, errors='replace')


def _tree_entries(ref: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in _git('ls-tree', '-r', ref).splitlines():
        if not line:
            continue
        meta, path = line.split('\t', 1)
        _mode, obj_type, sha = meta.split()
        if obj_type == 'blob':
            entries.append((sha, path))
    return entries


def _unsafe_name(path: str) -> bool:
    p = Path(path)
    if p.name in FORBIDDEN_NAMES:
        return True
    if p.name.startswith('.env.') and p.name != '.env.example':
        return True
    return p.suffix.lower() in FORBIDDEN_SUFFIXES


def _scan_blob(sha: str) -> list[str]:
    try:
        data = subprocess.check_output(['git', 'cat-file', '-p', sha], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []
    if b'\x00' in data[:8192]:
        return []
    text = data.decode('utf-8', errors='replace')
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def scan_ref(ref: str, blob_cache: dict[str, list[str]]) -> list[str]:
    findings: list[str] = []
    for sha, path in _tree_entries(ref):
        if _unsafe_name(path):
            findings.append(f'{ref}: forbidden tracked path: {path}')
        labels = blob_cache.setdefault(sha, _scan_blob(sha))
        for label in labels:
            findings.append(f'{ref}: possible {label} in {path}')
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()

    blob_cache: dict[str, list[str]] = {}
    findings = scan_ref('HEAD', blob_cache)
    refs_scanned = 1
    unique_trees_scanned = 1
    if args.history:
        commits = [line for line in _git('rev-list', '--all').splitlines() if line]
        refs_scanned = len(commits)
        seen_trees: set[str] = set()
        findings = []
        for commit in commits:
            tree = _git('rev-parse', f'{commit}^{{tree}}').strip()
            if tree in seen_trees:
                continue
            seen_trees.add(tree)
            findings.extend(scan_ref(commit, blob_cache))
        unique_trees_scanned = len(seen_trees)

    deduped = sorted(set(findings))
    print(
        'public-readiness '
        f'refs_scanned={refs_scanned} '
        f'unique_trees_scanned={unique_trees_scanned} '
        f'unique_blobs_scanned={len(blob_cache)} '
        f'findings={len(deduped)}'
    )
    for finding in deduped:
        print(f'PUBLIC_READINESS_FINDING: {finding}')
    return 1 if deduped else 0


if __name__ == '__main__':
    raise SystemExit(main())
