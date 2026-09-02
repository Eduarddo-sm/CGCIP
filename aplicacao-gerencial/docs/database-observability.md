# Observabilidade do PostgreSQL

## Coleta automatica

O gerencial coleta uma fotografia operacional a cada 300 segundos. O intervalo pode ser alterado por `GERENCIAL_DB_MONITOR_INTERVAL_SECONDS`, com minimo de 60 segundos.

Cada fotografia registra:

- tamanho total do banco;
- conexoes totais, ativas e ociosas;
- uso percentual de `max_connections`;
- estatisticas do pool do gerencial;
- cache hit do PostgreSQL;
- commits, rollbacks, deadlocks e arquivos temporarios;
- locks aguardando liberacao;
- transacoes acima do limite;
- linhas estimadas, linhas mortas, tamanho e crescimento de cada tabela.

O historico fica em:

- `gerencial.database_health_snapshots`;
- `gerencial.database_table_growth_snapshots`.

A retencao padrao e 90 dias e pode ser alterada em `gerencial.db_retention_policies`, escopo `monitoring`.

## Limites e alertas

| Variavel | Padrao | Alerta |
| --- | ---: | --- |
| `GERENCIAL_DB_CONNECTION_WARNING_PERCENT` | 75 | Pressao de conexoes; critico em 90% |
| `GERENCIAL_DB_CACHE_WARNING_PERCENT` | 95 | Cache hit abaixo do esperado |
| `GERENCIAL_DB_LONG_TRANSACTION_SECONDS` | 60 | Transacao aberta alem do limite |
| `GERENCIAL_DB_DEAD_TUPLE_WARNING_PERCENT` | 20 | Linhas mortas, desde que existam ao menos 1.000 |

Locks aguardando liberacao geram alerta critico.

## Endpoints administrativos

- `GET /api/database/monitoring`: ultima coleta.
- `GET /api/database/monitoring/history?limit=96`: serie historica.
- `POST /api/database/monitoring/collect`: coleta imediata e auditada.
- `GET /api/database/inventory`: inventario de tabelas, linhas e tamanho.
- `GET /api/diagnostico`: inclui ultima coleta, pool, backups e manutencao.

Todos exigem usuario administrador.

## Leitura operacional

1. Conexoes acima de 75%: localizar sessoes ociosas e revisar tamanho do pool.
2. Transacoes longas: identificar o processo antes de encerrar; nao cancelar sem entender a operacao.
3. Locks: localizar bloqueador e bloqueado, preservar a transacao que representa gravacao valida.
4. Cache abaixo de 95%: observar por varias coletas antes de alterar memoria ou indices.
5. Crescimento abrupto: verificar importacoes, duplicidade, snapshots e logs.
6. Linhas mortas: confirmar se autovacuum esta executando antes de rodar manutencao manual.

## Verificacao rapida no DBeaver

```sql
SELECT *
FROM gerencial.database_health_snapshots
ORDER BY captured_at DESC
LIMIT 20;

SELECT schema_name, table_name, size_bytes, growth_bytes, growth_percent, captured_at
FROM gerencial.database_table_growth_snapshots
ORDER BY captured_at DESC, growth_bytes DESC
LIMIT 100;
```
