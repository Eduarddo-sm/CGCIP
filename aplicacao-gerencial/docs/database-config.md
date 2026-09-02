# Configuracao de Banco

Data: 2026-06-15

## Objetivo

Permitir que as aplicacoes continuem usando SQLite por padrao, mas fiquem preparadas para receber PostgreSQL via `DATABASE_URL`.

Este passo nao migra os dados e nao troca o banco em uso.

## Aplicacao Gerencial

Arquivo de configuracao:

```text
aplicacao-gerencial/backend/config.py
```

Exemplo:

```text
aplicacao-gerencial/.env.example
```

Padrao atual:

```env
DATABASE_URL=sqlite:///data/app.sqlite3
```

Futuro PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg://projeto_user:SENHA@127.0.0.1:5432/projeto_negocial
```

O repository do gerencial agora detecta SQLite ou PostgreSQL. Para PostgreSQL ele usa `psycopg` diretamente e o schema `gerencial`.

## Aplicacao Negocial

Arquivo de configuracao:

```text
aplicacao-negocial/backend/config.py
```

Exemplo:

```text
aplicacao-negocial/.env.example
```

Padrao atual:

```env
DATABASE_URL=sqlite:///database/negocial.sqlite3
```

Futuro PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg://projeto_user:SENHA@127.0.0.1:5432/projeto_negocial
```

O negocial ja usa SQLAlchemy. Foi ajustado para:

- aplicar `check_same_thread=False` somente quando o banco for SQLite;
- usar o schema `negocial` quando `DATABASE_URL` for PostgreSQL;
- manter schema vazio quando `DATABASE_URL` for SQLite.

## Proximo Passo

Adaptar a camada de acesso ao banco:

- Criar script de migracao dos dados atuais.
- Testar os dois sistemas contra um PostgreSQL local/intranet.
- Ajustar consultas pontuais que aparecerem nos testes reais com PostgreSQL.
