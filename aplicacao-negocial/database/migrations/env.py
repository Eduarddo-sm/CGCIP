from logging.config import fileConfig
import os
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool
import sqlalchemy as sa

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings
from backend.database import Base
from backend.models import (
    CarteiraColuna,
    CarteiraNegocial,
    Ferramenta,
    FerramentaCampo,
    FerramentaComentario,
    FerramentaEvento,
    FerramentaPermissao,
    FerramentaRegistro,
    FerramentaStatus,
    FerramentaTransicao,
    FerramentaVersao,
    AlphaHoCalculation,
    AlphaHoRuleVersion,
    AlphaMetaImport,
    AlphaPortfolioGoal,
    ParecerSolicitacao,
    ProducaoGamma,
    ProducaoCampo,
    ProducaoAlpha,
    ProducaoRegistro,
    ProducaoBeta,
    User,
    UserMonthlyGoal,
    UserSession,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
database_url = os.environ.get("DATABASE_URL", "").strip() or settings.database_url
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

MIGRATION_OPTIONS = {
    "target_metadata": target_metadata,
    "include_schemas": True,
    "version_table_schema": "negocial",
}


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True, **MIGRATION_OPTIONS)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        connection.execute(sa.text("CREATE SCHEMA IF NOT EXISTS negocial"))
        connection.commit()
        context.configure(connection=connection, **MIGRATION_OPTIONS)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
