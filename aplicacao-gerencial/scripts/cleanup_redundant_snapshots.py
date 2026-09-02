from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import settings
from database.repository import Repository
from services.database_backup import DatabaseBackupService
from services.snapshot_retention import SnapshotRetentionService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove snapshots sem evento, preservando o baseline mais recente de cada negociador/sheet."
    )
    parser.add_argument("--apply", action="store_true", help="Executa a limpeza. Sem esta opcao, apenas simula.")
    args = parser.parse_args()

    repository = Repository(settings.database_url)
    try:
        retention = SnapshotRetentionService(repository)
        inspection = retention.inspect()
        if not args.apply:
            print(json.dumps({"mode": "dry-run", **inspection}, ensure_ascii=False))
            return 0

        backup_service = DatabaseBackupService(settings.database_url, settings.data_dir)
        backup_result = backup_service.create_backup("pre_snapshot_cleanup")
        verification = backup_service.verify_backup(backup_result["backup"]["name"])
        if not verification.get("ok"):
            raise RuntimeError("O backup anterior a limpeza nao passou na verificacao.")
        result = retention.cleanup()
        print(json.dumps({
            "mode": "apply",
            "backup": backup_result["backup"],
            "verification": verification,
            "cleanup": result,
        }, ensure_ascii=False))
        return 0
    finally:
        repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
