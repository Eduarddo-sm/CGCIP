# Performance e monitoramento do PostgreSQL

## Migrations

Os schemas `gerencial` e `negocial` sao versionados por Alembic. Cada aplicacao executa `upgrade head`
antes de abrir o pool, protegida por `pg_advisory_lock`. O `Repository` semeia apenas
dados padrao; mudancas estruturais devem ser feitas em `database/migrations/versions`.

Comandos:

```powershell
$env:PYTHONPATH=".;..\aplicacao-negocial\.venv\Lib\site-packages"
python -m alembic current
python -m alembic upgrade head
```

Para validar o historico completo em um banco vazio:

```powershell
$env:POSTGRES_ADMIN_URL="postgresql://postgres:SENHA@127.0.0.1:5432/postgres"
python scripts/verify_migrations.py
..\aplicacao-negocial\.venv\Scripts\python.exe ..\aplicacao-negocial\scripts\verify_migrations.py
```

Os scripts criam e removem bancos isolados automaticamente. Falha de revision, schema
incompleto ou indice invalido deve bloquear a publicacao.

## pg_stat_statements

A extensao foi adicionada ao servidor. Ela exige reinicio do servico PostgreSQL para
carregar `shared_preload_libraries`. Em um PowerShell executado como Administrador:

```powershell
Restart-Service postgresql-x64-18
```

Depois valide:

```sql
SHOW shared_preload_libraries;
SELECT count(*) FROM pg_stat_statements;
```

O painel `Configuracao > Diagnostico` informa se a extensao esta instalada e carregada.
Sem ela, o painel continua exibindo scans, linhas mortas, crescimento e uso de indices.

## Alertas e heartbeat

O coletor roda a cada cinco minutos e persiste snapshots e alertas. Alertas possuem os
estados `open`, `acknowledged` e `resolved`; problemas que deixam de existir sao
resolvidos automaticamente na coleta seguinte.

O watchdog independente pode ser executado por um monitor externo ou Agendador de Tarefas:

```powershell
python scripts/database_watchdog.py --max-age-seconds 900
```

Para registrar o watchdog no Agendador de Tarefas a cada cinco minutos:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\instalar-monitoramento-banco.ps1
```

Codigos de saida: `0` saudavel e `2` heartbeat ausente ou atrasado.

## Teste de carga e SLO

O teste autenticado valida simultaneamente Gerencial e Negocial. Ele falha quando o p95,
a taxa de erro ou o throughput nao atendem aos limites definidos e grava um JSON em
`data/reports/load`.

```powershell
$env:GERENCIAL_LOAD_USERNAME="usuario"
$env:GERENCIAL_LOAD_PASSWORD="senha"
python scripts/load_test.py --users 25 --max-p95-ms 500 --max-auth-p95-ms 1500 --max-error-percent 1 --min-throughput 5
```

O p95 de negocio exclui login/logout. A autenticacao tem SLO separado porque o hashing
de senha e intencionalmente mais caro e nao deve ser enfraquecido para reduzir latencia.
