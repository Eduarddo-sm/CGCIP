# Backup, Restore e Recuperacao de Desastre

## Objetivos operacionais

- RPO atual: ate 24 horas, conforme backup automatico diario.
- RTO alvo: ate 60 minutos para restauracao completa e validacao funcional.
- Retencao: 90 dias, mantendo ao menos os 30 dumps mais recentes.
- Formato: dump customizado do PostgreSQL, com SHA-256 registrado.

## Backup

O gerencial cria dumps em `data/backups/database`. Cada novo backup retorna nome, tamanho e SHA-256. Antes de uma restauracao no banco ativo, o sistema cria automaticamente um dump `pre_restore`.

Criacao administrativa pela API:

```text
POST /api/backups/database
```

## Ensaio isolado de restauracao

Executar na pasta da aplicacao gerencial:

```powershell
python scripts/verify_backup_restore.py --create
```

O ensaio:

1. exporta um snapshot PostgreSQL consistente;
2. cria um dump customizado;
3. tenta restaurar em banco temporario;
4. se o usuario nao possuir `CREATEDB`, usa schemas temporarios isolados;
5. compara todas as tabelas, contagens, views, constraints, indices e migration;
6. remove o ambiente temporario;
7. grava um relatorio JSON em `data/reports/database`.

Para isolamento em banco separado, um DBA pode conceder temporariamente `CREATEDB` ao usuario de manutencao. A aplicacao normal nao precisa dessa permissao.

## Resultado validado em 2026-07-20

- 40 tabelas restauradas;
- 212.496 registros comparados;
- 356 constraints;
- 140 indices;
- 1 view;
- contagens id?nticas ao snapshot de origem;
- ambiente isolado removido ao final;
- SHA-256 do dump registrado no relatorio.

Relatorio: `data/reports/database/restore_validation_20260720_153354.json`.

## Procedimento de recuperacao real

1. Declarar o incidente e impedir novas gravacoes nos dois sistemas.
2. Registrar horario, sintomas e ultimo backup conhecido.
3. Criar um backup do estado atual, mesmo que aparentemente inconsistente.
4. Executar o ensaio isolado no dump escolhido.
5. Conferir `ok: true`, hash, contagens e migration no relatorio.
6. Restaurar pelo endpoint protegido `POST /api/backups/database/restore`, com confirmacao critica e motivo.
7. Reiniciar os dois servicos para renovar pools e caches.
8. Validar login, producao, pareceres, protocolos, colchao, timeline e auditoria.
9. Liberar gravacoes e registrar o encerramento do incidente.

## Rollback da recuperacao

Se a verificacao funcional falhar, restaurar o dump `pre_restore` criado imediatamente antes da operacao e repetir a validacao. Nunca sobrescrever ou apagar o dump que originou o incidente.

## Checklist mensal

- Executar `verify_backup_restore.py --create`.
- Confirmar que o relatorio terminou com `ok: true`.
- Confirmar que o ambiente temporario foi removido.
- Revisar falhas do job `database_backup` no diagnostico.
- Conferir espaco em disco e politica de retencao.
- Guardar uma copia mensal fora da maquina do servidor.
