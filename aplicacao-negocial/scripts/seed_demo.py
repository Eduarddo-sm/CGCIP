"""Create an idempotent set of synthetic records for local demonstrations."""

from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import SessionLocal
from backend.models import (
    CarteiraColuna,
    CarteiraNegocial,
    ProducaoCampo,
    ProducaoGamma,
    ProducaoRegistro,
    User,
)
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

DEMO_COLUMNS = (
    {"chave": "DATA", "nome": "Data", "tipo": "data", "automatico": True, "auto_tipo": "today", "mostrar_cadastro": False},
    {"chave": "NPJ", "nome": "NPJ", "tipo": "texto", "obrigatoria": True, "identificador": True, "cadastro_etapa": 1},
    {"chave": "CLIENTE", "nome": "Cliente", "tipo": "texto", "obrigatoria": True, "cadastro_etapa": 1},
    {"chave": "VALOR_TOTAL", "nome": "Valor do acordo", "tipo": "moeda", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "ENTRADA", "nome": "Entrada", "tipo": "moeda", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "VALOR_HO", "nome": "Honorarios", "tipo": "moeda", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "TIPO_DE_ACORDO", "nome": "Tipo de acordo", "tipo": "select", "obrigatoria": True, "opcoes": ["A_VISTA", "PARCELADO"], "cadastro_etapa": 1},
    {"chave": "VENCIMENTO", "nome": "Vencimento", "tipo": "data", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "STATUS", "nome": "Status", "tipo": "select", "obrigatoria": True, "opcoes": ["PROPOSTA", "AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO", "PROPOSTA_NEGADA", "QUEBRA"], "cadastro_etapa": 2},
    {"chave": "NEGOCIADOR", "nome": "Negociador", "tipo": "texto", "automatico": True, "auto_tipo": "usuario", "mostrar_cadastro": False},
)


def ensure_demo_schema(db) -> dict[str, CarteiraColuna]:
    carteira = db.query(CarteiraNegocial).filter(CarteiraNegocial.nome == "GAMMA").first()
    if carteira is None:
        carteira = CarteiraNegocial(
            nome="GAMMA",
            slug="GAMMA",
            descricao="Carteira sintetica para demonstracao local.",
            active=True,
            modo_schema=True,
        )
        db.add(carteira)
        db.flush()
    else:
        carteira.active = True
        carteira.modo_schema = True
        carteira.slug = "GAMMA"

    columns = {column.chave: column for column in carteira.colunas}
    for order, config in enumerate(DEMO_COLUMNS, start=1):
        column = columns.get(config["chave"])
        if column is None:
            column = CarteiraColuna(carteira_id=carteira.id, chave=config["chave"], nome=config["nome"])
            db.add(column)
            columns[config["chave"]] = column
        column.nome = config["nome"]
        column.tipo = config["tipo"]
        column.obrigatoria = bool(config.get("obrigatoria", False))
        column.identificador = bool(config.get("identificador", False))
        column.visivel = bool(config.get("visivel", True))
        column.ordem = order
        column.automatico = bool(config.get("automatico", False))
        column.auto_tipo = config.get("auto_tipo")
        column.max_length = config.get("max_length")
        column.mostrar_cadastro = bool(config.get("mostrar_cadastro", True))
        column.cadastro_etapa = int(config.get("cadastro_etapa", 2))
        column.opcoes_json = json.dumps(config.get("opcoes", []), ensure_ascii=True)

    db.flush()
    return columns


def sync_dynamic_fields(db, record: ProducaoRegistro, columns: dict[str, CarteiraColuna]) -> None:
    values = {
        "DATA": record.data_acordo,
        "NPJ": record.gamma.npj,
        "CLIENTE": record.cliente,
        "VALOR_TOTAL": record.valor_total_acordo,
        "ENTRADA": record.valor_entrada,
        "VALOR_HO": record.gamma.valor_ho,
        "TIPO_DE_ACORDO": record.tipo_acordo,
        "VENCIMENTO": record.data_vencimento,
        "STATUS": record.status,
        "NEGOCIADOR": record.user.username,
    }
    for key, value in values.items():
        column = columns[key]
        field = db.get(ProducaoCampo, (record.id, column.id))
        if field is None:
            field = ProducaoCampo(producao_id=record.id, coluna_id=column.id)
            db.add(field)
        field.valor_texto = None
        field.valor_numero = None
        field.valor_data = None
        field.valor_json = None
        if column.tipo in {"numero", "moeda"}:
            field.valor_numero = Decimal(value)
        elif column.tipo == "data":
            field.valor_data = value
        else:
            field.valor_texto = str(value)


def main() -> None:
    run_schema_migrations(settings.database_url, ROOT_DIR)
    create_database()

    with SessionLocal() as db:
        owner = db.query(User).order_by(User.id).first()
        if owner is None:
            raise RuntimeError(
                "Crie o usuario administrador com database/seed.py antes de carregar os dados demo."
            )

        columns = ensure_demo_schema(db)

        today = date.today()
        competence = today.replace(day=1)
        existing = {
            record.cliente: record
            for record in db.query(ProducaoRegistro)
            .filter(ProducaoRegistro.origem_registro == DEMO_SOURCE)
            .all()
        }
        for index, (client, status, total, entry, fee, due_offset) in enumerate(DEMO_ROWS, start=1):
            agreement_date = today - timedelta(days=20 - index)
            payment_date = agreement_date + timedelta(days=3) if status == "PAGAMENTO_REALIZADO" else None
            record = existing.get(client)
            if record is None:
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
                db.flush()
            sync_dynamic_fields(db, record, columns)

        db.commit()
        print(f"{len(DEMO_ROWS)} acordos sinteticos sincronizados para {owner.username}.")


if __name__ == "__main__":
    main()
