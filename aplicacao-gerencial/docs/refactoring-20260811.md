# Refatoracao e saneamento de 11/08/2026

## Dados

- A criacao de snapshots passou a ocorrer somente quando existe delta real.
- A limpeza protege snapshots referenciados por eventos e o baseline mais recente de cada negociador/sheet.
- Foram removidos 198.142 snapshots redundantes: de 199.643 para 1.501 registros.
- A tabela `gerencial.snapshots` caiu de aproximadamente 369 MB para 8,5 MB apos `VACUUM FULL`.
- A retencao diaria cobre sessoes, leituras, snapshots elegiveis e historico de observabilidade.
- Usuarios agora possuem unicidade case-insensitive nos schemas gerencial e negocial.

## Seguranca e schema

- Nao existem mais credenciais administrativas padrao no codigo.
- O bootstrap de uma base vazia exige variaveis de ambiente e senha forte.
- O verificador de migrations deriva o head dos arquivos e valida uma base PostgreSQL isolada.
- Migrations adicionaram unicidade por `lower(username)` e resolveram colisoes existentes sem apagar dados.

## Arquitetura

- `backend/app_state.py` concentra composicao e jobs; `backend/server.py` permanece focado no protocolo HTTP.
- `database/connection.py` e `database/permissions.py` retiram infraestrutura e politica da fachada `Repository`.
- Presets e normalizadores do construtor estao em `ferramentaBuilderDefinitions.js`.
- O CSS do construtor foi dividido em core, registros, estudio, workspace e decisao.
- `shared/frontend/excelGrid.js` e a fonte canonica sincronizada para os dois sistemas.

## Qualidade

- O E2E do formulario dinamico aguarda o schema antes de abrir o cadastro.
- `scripts/check-project.ps1` valida sincronizacao do grid, testes Python e contratos JavaScript dos dois sistemas.
- Capturas amplas permanecem apenas onde falhas externas precisam ser traduzidas; rotinas de manutencao registram stack trace e seguem observaveis.
