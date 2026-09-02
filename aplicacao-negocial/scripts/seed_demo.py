"""Create an idempotent set of synthetic records for local demonstrations."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import SessionLocal
from backend.models import ProducaoGamma, ProducaoRegistro, User
from backend.services.bootstrap_service import create_database
from backend.services.schema_migration_service import run_schema_migrations
from backend.config import settings


DEMO_SOURCE = "DEMO_SEED"
DEMO_ROWS = (
    ("EMPRESA DEMO ALFA LTDA", "PAGAMENTO_REALIZADO", "56000.00", "8000.00", "5600.00", -18),
    ("EMPRESA DEMO BETA LTDA", "AGUARDANDO_PAGAMENTO", "79000.00", "12000.00", "7900.00", -12),
    ("EMPRESA DEMO GAMA LTDA", "PROPOSTA", "33500.00", "5000.00", "3350.00", -8),
    ("EMPRESA DEMO DELTA LTDA", "PROPOSTA_NEGADA", "40000.00", "4000.00", "4000.00", -5),
    ("EMPRESA DEMO EPSILON LTDA", "QUEBRA", "28000.00", "4500.00", "2800.00", -3),
    ("EMPRESA DEMO ZETA LTDA", "AGUARDANDO_PAGAMENTO", "65000.00", "10000.00", "6500.00", 4),
)


def main() -> None:
    run_schema_migrations(settings.database_url, ROOT_DIR)
    create_database()

    with SessionLocal() as db:
        owner = db.query(User).order_by(User.id).first()
        if owner is None:
            raise RuntimeError(
                "Crie o usuario administrador com database/seed.py antes de carregar os dados demo."
            )

        if db.query(ProducaoRegistro).filter(ProducaoRegistro.origem_registro == DEMO_SOURCE).first():
            print("Dados demonstrativos ja existem; nenhuma alteracao foi feita.")
            return

        today = date.today()
        competence = today.replace(day=1)
        for index, (client, status, total, entry, fee, due_offset) in enumerate(DEMO_ROWS, start=1):
            agreement_date = today - timedelta(days=20 - index)
            payment_date = agreement_date + timedelta(days=3) if status == "PAGAMENTO_REALIZADO" else None
            record = ProducaoRegistro(
                data_acordo=agreement_date,
                competencia=competence,
                cliente=client,
                valor_total_acordo=Decimal(total),
                valor_entrada=Decimal(entry),
                tipo_acordo="PARCELADO" if index % 2 == 0 else "A_VISTA",
                data_vencimento=today + timedelta(days=due_offset),
                data_pagamento=payment_date,
                status=status,
                justificativa_status="Registro sintetico para demonstracao.",
                carteira="GAMMA",
                user_id=owner.id,
                origem_registro=DEMO_SOURCE,
            )
            record.gamma = ProducaoGamma(
                npj=f"DEMO-{index:04d}",
                gecor=f"G-{4900 + index}",
                valor_ho=Decimal(fee),
                percentual_ho=Decimal("10.00"),
                autorizacao_flexibilizacao="NAO",
            )
            db.add(record)

        db.commit()
        print(f"{len(DEMO_ROWS)} acordos sinteticos adicionados para {owner.username}.")


if __name__ == "__main__":
    main()
