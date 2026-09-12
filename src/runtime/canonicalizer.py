from __future__ import annotations

from src.runtime import canonicalizer_legacy as _legacy

# Preserve the existing module surface, including private helper names used by
# tests and diagnostics, while routing only the public canonicalization entry
# point through the validated optimized implementation.
for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

from src.runtime.canonicalizer_fast import canonicalize_records as canonicalize_records
