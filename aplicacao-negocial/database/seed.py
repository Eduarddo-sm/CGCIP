from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import SessionLocal
from backend.services.bootstrap_service import create_database, seed_admin_user
from backend.config import settings
from backend.services.schema_migration_service import run_schema_migrations


def main():
    run_schema_migrations(settings.database_url, ROOT_DIR)
    create_database()
    db = SessionLocal()
    try:
        admin = seed_admin_user(db)
        print(f"Usuario admin pronto: {admin.username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
