# Arquitetura da Aplicacao Gerencial

## Fluxo principal

```text
Browser
  -> ui/app.js
  -> ui/features/*
  -> /api/*
  -> backend/routes/*
  -> services/*
  -> database/repository.py ou PostgreSQL negocial
```

## Fronteiras

### UI

- `ui/core`: API, estado, cache, carregamento, notificacoes visuais e sincronizacao.
- `ui/layout`: sidebar, perfil, tema, dialogs e navegacao entre ferramentas.
- `ui/features`: comportamento por dominio.
- `ui/templates`: estrutura HTML carregada sob demanda.
- `ui/styles/modules`: estilos especificos por dominio.
- `shared/frontend/excelGrid.js`: fonte canonica da grade compartilhada; os arquivos estaticos dos dois sistemas sao espelhos gerados.
- `ui/styles/design-system.css`: tokens e componentes compartilhados.
- `ui/app.css`: manifesto unico, na ordem oficial da cascata.

### Backend

- `backend/server.py`: protocolo HTTP, autenticacao e compatibilidade das rotas ainda nao extraidas.
- `backend/app_state.py`: composicao dos servicos e ciclo das tarefas de manutencao.
- `backend/routes`: despacho por dominio. Novas rotas devem nascer aqui.
- `services`: regras de negocio e integracoes externas.
- `database/connection.py`: adaptacao de conexoes SQLite/PostgreSQL.
- `database/permissions.py`: catalogo e matriz padrao de permissoes.
- `database/repository.py`: fachada de persistencia gerencial; novos agregados devem nascer em repositorios menores.

### Dados

- Schema gerencial: usuarios, sessoes, negociadores, snapshots, eventos, leituras e auditoria.
- Schema negocial: usuarios negociadores, carteiras, schemas versionados, producao e pareceres.
- Dados de producao usam uma estrutura orientada a schema de carteira; nao deve ser criada uma tabela fisica por nova carteira.

## Sincronizacao

O frontend usa um coordenador unico em `ui/core/syncCoordinator.js`:

- pausa atualizacoes quando a aba esta oculta;
- impede ciclos concorrentes;
- atualiza somente a tela ativa;
- consulta notificacoes em cadencia separada;
- reaproveita `version` e cache nas APIs que suportam resposta sem alteracao.

## Backups e retencao

- Backups do banco sao administrados por `DatabaseBackupService`.
- Backups Excel usam `BackupRetentionService`.
- A politica padrao preserva arquivos recentes e um limite por origem.
- A manutencao remove sessoes expiradas, leituras antigas e snapshots sem referencia conforme politica explicita.

## Regras para evolucao

1. Nao adicionar novos blocos de dominio em `backend/server.py`; criar ou ampliar uma rota em `backend/routes`.
2. Nao adicionar novos intervalos globais no frontend; registrar a necessidade no coordenador de sincronizacao.
3. Nao inserir CSS global de uma ferramenta em `styles.css`; usar seu modulo e os tokens do design system.
4. Mudancas de schema de carteira devem ser versionadas e nao destrutivas quando houver dados.
5. Toda operacao administrativa destrutiva deve exigir permissao, confirmacao e auditoria.
6. Capturas amplas de excecao so sao aceitas em fronteiras HTTP, COM/Excel, jobs e integracoes; devem registrar contexto antes de traduzir a falha.
