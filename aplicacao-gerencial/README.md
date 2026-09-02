# Aplicacao Gerencial

Painel de backoffice para monitoramento da producao negocial, pareceres, protocolos, colchao, auditoria e administracao de usuarios e carteiras.

## Arquitetura atual

- Backend HTTP em Python, iniciado por `app.py`.
- Persistencia principal em PostgreSQL, configurada por `DATABASE_URL`.
- SQLite permanece disponivel somente como modo local de compatibilidade e testes.
- Frontend modular em JavaScript nativo, templates HTML por grupo e CSS organizado por modulo.
- Integracoes Excel isoladas nos servicos de Parecer e Colchao.
- Autenticacao por sessao, permissoes por perfil e sobrescritas por usuario.
- Auditoria, backups do banco, retencao de arquivos e manutencao de dados.

Mais detalhes em [docs/architecture.md](docs/architecture.md).

## Configuracao

Crie um arquivo `.env` local. Nao salve senhas reais no repositorio.

```env
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@SERVIDOR:5432/projeto_negocial
NEGOCIADORES_DATA_DIR=data
NEGOCIADORES_UI_DIR=ui
```

Para desenvolvimento isolado, ainda e possivel usar:

```env
DATABASE_URL=sqlite:///data/app.sqlite3
```

## Execucao

```powershell
python app.py
```

Por padrao, a interface fica disponivel em `http://127.0.0.1:8765`. Para acesso na intranet, use o nome DNS da maquina ou o endereco definido pela rede.

## Testes

```powershell
python -m unittest discover -s tests -v
$env:GERENCIAL_E2E_USERNAME="usuario"
$env:GERENCIAL_E2E_PASSWORD="senha"
npm run test:e2e
```

Os testes de repositorio usam um SQLite temporario e nunca alteram o PostgreSQL de producao. O E2E usa o Chrome instalado para validar login e navegacao entre os modulos sem modificar registros.

O teste integrado dos dois servidores fica na raiz do projeto:

```powershell
python ..\scripts\smoke_systems.py
```

## Migracao e manutencao

- `scripts/migrate_sqlite_to_postgres.py`: migracao controlada do legado SQLite.
- `scripts/migrate_protocolo_excel.py`: importacao inicial dos protocolos do Excel.
- `scripts/recover_colchao.py`: recuperacao assistida dos arquivos do Colchao.
- Grupo Configuracao: auditoria, diagnostico, backups, restore e manutencao.
- Backup PostgreSQL automatico diario e retencao especifica de dumps.
- Logs JSON com `X-Request-ID`, duracao e status de cada requisicao.
- Endpoints `/api/health/live` e `/api/health/ready`.

## Seguranca operacional

- Mantenha `.env` fora de compartilhamentos publicos.
- Use uma conta PostgreSQL exclusiva da aplicacao e limite o acesso a rede interna.
- Teste o restore periodicamente; backup sem teste de restauracao nao e garantia de recuperacao.
- Ensaio completo: `python scripts/verify_backup_restore.py --create`.
- Monitoramento PostgreSQL: `/api/database/monitoring` e `/api/database/monitoring/history`.
- Documentacao: `docs/database-model.md`, `docs/database-observability.md` e `docs/disaster-recovery.md`.
- Antes de alteracoes em arquivos Excel, preserve a copia automatica criada pela aplicacao.
