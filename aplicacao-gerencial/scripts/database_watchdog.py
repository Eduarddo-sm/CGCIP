from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Confere o heartbeat independente do coletor gerencial.")
    parser.add_argument("--max-age-seconds", type=int, default=900)
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    load_env()
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(url, row_factory=dict_row) as conn:
        row = conn.execute("SELECT id, captured_at FROM gerencial.database_health_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1").fetchone()
    age = None if not row else max(0, int((datetime.now(timezone.utc) - row["captured_at"].astimezone(timezone.utc)).total_seconds()))
    payload = {
        "ok": age is not None and age <= args.max_age_seconds,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "last_snapshot_id": None if not row else row["id"],
        "last_captured_at": None if not row else row["captured_at"].isoformat(),
        "age_seconds": age,
        "max_age_seconds": args.max_age_seconds,
    }
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
