# Aplicacao Negocial

Aplicacao operacional para producao diaria e solicitacao de pareceres. Os dados sao persistidos no PostgreSQL e consumidos pelo Gerencial.

## Arquitetura

- FastAPI com rotas separadas por dominio.
- SQLAlchemy e Alembic sobre o schema PostgreSQL `negocial`.
- Autenticacao JWT em cookie HttpOnly e sessoes revogaveis.
- Carteiras e colunas configuradas por schema dinamico.
- Producao dividida em validacao, calendario, serializacao e persistencia.
- Frontend JavaScript modular com grid Excel-like.
- Sincronizacao leve por versoes operacionais.
- Auditoria das alteracoes de producao, parecer e autenticacao.
- Logs JSON, `X-Request-ID` e health checks de processo e banco.

SQLite existe apenas para desenvolvimento isolado e compatibilidade. O ambiente de producao usa `DATABASE_URL` PostgreSQL.

## Configuracao

Crie `.env` a partir de `.env.example`. Nao grave credenciais reais no repositorio.

```env
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@SERVIDOR:5432/projeto_negocial
JWT_SECRET_KEY=CHAVE_ALEATORIA_COM_PELO_MENOS_48_CARACTERES
```

Quando `JWT_SECRET_KEY` nao e informada, uma chave forte e persistente e criada em `database/.jwt_secret`.

## Execucao

```powershell
.\iniciar_negocial.ps1
```

Ou:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8890 --no-access-log
```

- Aplicacao: `http://127.0.0.1:8890`
- Liveness: `http://127.0.0.1:8890/api/health/live`
- Readiness: `http://127.0.0.1:8890/api/health/ready`

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
npm test
```

Os testes Python cobrem permissoes, auditoria, valores dinamicos, datas, calendario e regras de H.O. Os testes JavaScript validam a ligacao de todos os modulos e o contrato da coluna Status.

## Dominios

### Producao diaria

- Cadastro em duas etapas configurado pelo schema da carteira.
- Competencias mensais e regra opcional de envio ao proximo mes.
- Status alteravel no grid com justificativa/data obrigatoria quando aplicavel.
- Validacao de identificadores, dinheiro, datas e selects.
- Prevencao de duplicidade por carteira e competencia.
- Atualizacao dinamica por versao sem recarregar a pagina.

### Pareceres

- Solicitacao pelo negociador.
- Fluxo de aprovacao/reprovacao no Gerencial.
- Status e justificativas sincronizados com o Negocial.

### Carteiras

GAMMA, Alpha, Beta e novas carteiras usam o mesmo modelo de schema dinamico. Colunas automaticas, obrigatorias, visiveis e etapas de cadastro sao controladas pelo Gerencial.
