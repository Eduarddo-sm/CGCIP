# Migracao SQLite para PostgreSQL

Script:

```text
scripts/migrate_sqlite_to_postgres.py
```

## O Que Ele Faz

Migra os dados atuais de:

```text
aplicacao-gerencial/data/app.sqlite3
aplicacao-negocial/database/negocial.sqlite3
```

para um PostgreSQL unico com os schemas:

```text
gerencial
negocial
```

## O Que Nao Migra

As tabelas de sessao nao sao migradas:

```text
gerencial.sessions
negocial.sessions
```

Motivo: na virada para PostgreSQL, e mais seguro obrigar todos os usuarios a fazer login novamente.

## Validar Sem Migrar

Use:

```powershell
& '.\.venv\Scripts\python.exe' scripts\migrate_sqlite_to_postgres.py --dry-run
```

Isso:

- le os dois SQLite;
- valida valores que podem bater em `CHECK` ou FK;
- mostra contagens por tabela;
- nao escreve nada em PostgreSQL.

## Migrar Para PostgreSQL

Exemplo:

```powershell
& '.\.venv\Scripts\python.exe' scripts\migrate_sqlite_to_postgres.py `
  --database-url "postgresql://projeto_user:SENHA@127.0.0.1:5432/projeto_negocial"
```

Tambem aceita URL SQLAlchemy:

```text
postgresql+psycopg://projeto_user:SENHA@127.0.0.1:5432/projeto_negocial
```

O script normaliza automaticamente para `postgresql://`.

## Resetar Schemas Antes de Migrar

Para ambiente de teste, pode limpar os schemas antes:

```powershell
& '.\.venv\Scripts\python.exe' scripts\migrate_sqlite_to_postgres.py `
  --database-url "postgresql://projeto_user:SENHA@127.0.0.1:5432/projeto_negocial" `
  --reset
```

Atencao: `--reset` executa:

```sql
DROP SCHEMA IF EXISTS gerencial CASCADE;
DROP SCHEMA IF EXISTS negocial CASCADE;
```

Use somente em banco de teste ou antes da virada oficial.

## Conversoes Aplicadas

- `active`: `1/0` para `true/false`;
- JSON texto para `JSONB`;
- `Alpha` para `ALPHA`;
- roles do negocial para maiusculo;
- roles do gerencial para minusculo;
- valores financeiros para `NUMERIC`;
- sessoes ignoradas.

## Ordem de Carga

1. `negocial.users`
2. `negocial.producao_diaria`
3. `negocial.pareceres`
4. `gerencial.users`
5. `gerencial.negociadores`
6. `gerencial.snapshots`
7. `gerencial.events`
8. `gerencial.overview_reads`
9. `gerencial.notification_reads`
10. `gerencial.notes`

## Proximo Passo Depois da Migracao

Apontar temporariamente os sistemas para PostgreSQL via `.env`:

```env
DATABASE_URL=postgresql+psycopg://projeto_user:SENHA@127.0.0.1:5432/projeto_negocial
```

Depois testar login, producao diaria, pareceres, overview, timeline e notificacoes.
