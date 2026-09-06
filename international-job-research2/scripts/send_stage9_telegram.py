from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reporting.telegram import check_configuration, send_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 9 Telegram reporting")
    parser.add_argument("--summary")
    parser.add_argument("--report")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(check_configuration(), ensure_ascii=False))
        return
    if not args.summary:
        parser.error("--summary is required unless --check is used")
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    send_report(summary, Path(args.report) if args.report else None)
    print(json.dumps({"ok": True, "delivered": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
