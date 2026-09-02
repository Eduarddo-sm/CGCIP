# Mapa do Banco de Dados

O antigo mapeamento SQLite foi aposentado apos a migracao para PostgreSQL.

A documentacao atual esta dividida em:

- `database-model.md`: entidades, relacionamentos e regras de integridade;
- `database-architecture.md`: limites dos schemas e manutencao;
- `database-observability.md`: performance, conexoes e crescimento;
- `disaster-recovery.md`: backup, restauracao e resposta a incidentes;
- `sqlite-to-postgres-migration.md`: historico da migracao, sem valor operacional atual.

A fonte de verdade estrutural do schema `negocial` sao as migrations Alembic. O schema `gerencial` e inicializado e endurecido pelo `database.repository.Repository`.
