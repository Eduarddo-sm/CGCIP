# CIP - Controle Inteligente de Produção

[![CI](https://github.com/Eduarddo-sm/projeto-negocial-showcase/actions/workflows/ci.yml/badge.svg)](https://github.com/Eduarddo-sm/projeto-negocial-showcase/actions/workflows/ci.yml)

Plataforma integrada para operacao negocial, acompanhamento de producao e
inteligencia gerencial. Esta edicao publica foi preparada para portfolio e usa
somente nomes, carteiras e identificadores sinteticos.

> Este repositorio e uma demonstracao tecnica independente. As carteiras
> `ALPHA`, `BETA` e `GAMMA`, empresas e usuarios exibidos nao representam
> organizacoes ou pessoas reais. Dados e integracoes operacionais nao fazem
> parte desta edicao.

## Destaques do projeto

- duas aplicacoes integradas para operacao e gestao;
- construtor de ferramentas e dashboards configuraveis;
- producao diaria, metas mensais, relatorios PDF e analise comparativa;
- fluxos de aprovacao, pendencias, protocolos e cronogramas financeiros;
- PostgreSQL e SQLite, migracoes Alembic, auditoria e rotacao de backups;
- frontend modular em JavaScript sem dependencia de framework visual;
- testes automatizados de backend, regras de negocio e contratos do frontend;
- credenciais locais fora do Git e senhas de planilhas criptografadas em repouso.

```mermaid
flowchart LR
    N[Aplicacao Negocial] --> API[Servicos e regras de negocio]
    G[Aplicacao Gerencial] --> API
    API --> DB[(PostgreSQL ou SQLite)]
    G --> XLS[Excel e relatorios]
    API --> AUD[Auditoria e observabilidade]
```

## Escopo da edicao publica

O codigo demonstra arquitetura, interface, testes e regras genericas. Scripts
de importacao historica, caminhos de rede, mapeamentos de colaboradores e dados
de operacoes reais foram removidos. Consulte [SECURITY.md](SECURITY.md) antes de
enviar qualquer contribuicao ou relato.

## Inicio rapido

Clone a edicao publica e entre na pasta:

```powershell
git clone https://github.com/Eduarddo-sm/projeto-negocial-showcase.git
cd projeto-negocial-showcase
```

Para avaliar as duas aplicacoes integradas, siga a configuracao PostgreSQL das
secoes seguintes. Depois de criar os arquivos `.env`, inicialize o banco e,
opcionalmente, carregue seis acordos sinteticos:

```powershell
cd aplicacao-negocial
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe database\seed.py
.\.venv\Scripts\python.exe scripts\seed_demo.py
cd ..\aplicacao-gerencial
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
.\iniciar-sistemas.ps1
```

O `database\seed.py` exige `ADMIN_USERNAME`, `ADMIN_PASSWORD` e uma
`JWT_SECRET_KEY` definidos no `.env` do Negocial. A carga demo pode ser executada
novamente sem duplicar registros.

Guia unico de instalacao, configuracao e operacao das aplicacoes **Negocial** e
**Gerencial**. Ao concluir este documento, os dois sistemas estarao rodando
localmente e, opcionalmente, acessiveis por outros computadores da rede interna.

## 1. Visao geral

O projeto possui duas aplicacoes web que usam o mesmo banco PostgreSQL:

| Aplicacao | Finalidade | Porta padrao | Endereco local |
|---|---|---:|---|
| Negocial | Operacao diaria dos negociadores | 8890 | `http://127.0.0.1:8890` |
| Gerencial | Backoffice, dashboards e configuracoes | 8765 | `https://127.0.0.1:8765` |

Principais tecnologias:

- Python 3.12;
- PostgreSQL;
- FastAPI, Uvicorn, SQLAlchemy e Alembic no Negocial;
- servidor Python e frontend JavaScript modular no Gerencial;
- Node.js para testes de JavaScript, Playwright e empacotamento opcional;
- Excel/OpenPyXL para recursos de planilhas.

Estrutura esperada:

```text
projeto-negocial-showcase/
|-- aplicacao-negocial/
|-- aplicacao-gerencial/
|-- scripts/
|-- shared/
|-- iniciar-sistemas.ps1
|-- instalar-inicializacao.ps1
`-- README.md
```

## 2. Sistema operacional

O ambiente recomendado e **Windows 10 ou Windows 11 de 64 bits**. O servidor web
e o banco podem ser executados em outros sistemas, mas os recursos que controlam
o Microsoft Excel por COM dependem de Windows e Excel instalado.

Para usar todas as funcionalidades, incluindo sincronizacao com arquivos Excel,
instale o Microsoft Excel no computador que executara o Gerencial.

## 3. Pre-requisitos

Instale os seguintes programas:

1. **Python 3.12 x64**: marque `Add Python to PATH` durante a instalacao.
2. **PostgreSQL 16 ou superior**: inclua Server, pgAdmin e Command Line Tools.
3. **Node.js 20 ou superior**: necessario para testes e Playwright; nao e exigido
   para apenas abrir os sistemas no navegador.
4. **Git**: opcional, mas recomendado para obter e atualizar o codigo.
5. **Microsoft Excel**: opcional para o nucleo web, necessario para integracoes
   que editam planilhas pela aplicacao instalada.

Confirme as instalacoes em um PowerShell novo:

```powershell
python --version
node --version
npm --version
psql --version
```

Se `psql` nao for reconhecido, adicione ao `PATH` a pasta `bin` da instalacao,
por exemplo `C:\Program Files\PostgreSQL\18\bin`, e abra outro PowerShell.

## 4. Obter o projeto

Coloque a pasta completa em um caminho local. Evite executar o codigo diretamente
de uma unidade de rede ou pasta sincronizada enquanto o sistema estiver ativo.

Exemplo:

```text
C:\Sistemas\projeto-negocial-showcase
```

Todos os comandos seguintes partem dessa pasta:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase"
```

Se o projeto for obtido por Git, clone o repositorio e confirme que as pastas
`aplicacao-negocial` e `aplicacao-gerencial` foram recebidas. A URL do repositorio
deve ser fornecida pelo responsavel pelo codigo.

## 5. Criar o banco PostgreSQL

O modo recomendado usa um unico banco chamado `projeto_negocial`. As aplicacoes
mantem seus objetos nos schemas `negocial` e `gerencial`.

### 5.1 Criacao pelo pgAdmin

1. Abra o pgAdmin e conecte-se ao PostgreSQL local.
2. Crie um usuario de login chamado `projeto_user` com uma senha forte.
3. Crie o banco `projeto_negocial` e defina `projeto_user` como proprietario.

### 5.2 Criacao pelo psql

Abra o PowerShell e entre com o usuario administrador do PostgreSQL:

```powershell
psql -U postgres -h 127.0.0.1
```

Execute, substituindo a senha:

```sql
CREATE ROLE projeto_user WITH LOGIN PASSWORD 'COLOQUE_UMA_SENHA_FORTE';
CREATE DATABASE projeto_negocial OWNER projeto_user ENCODING 'UTF8';
\c projeto_negocial
CREATE SCHEMA IF NOT EXISTS negocial AUTHORIZATION projeto_user;
CREATE SCHEMA IF NOT EXISTS gerencial AUTHORIZATION projeto_user;
GRANT ALL ON SCHEMA negocial, gerencial TO projeto_user;
```

Saia com `\q`.

Se a senha possuir `@`, `:`, `/`, `#`, `%` ou outros caracteres reservados de URL,
codifique-a antes de montar `DATABASE_URL`. Outra opcao e gerar uma senha forte
com letras, numeros, `_` e `-`.

## 6. Ambientes Python

Cada aplicacao possui seu proprio ambiente virtual. Nao reutilize um `.venv`
copiado de outro computador.

### 6.1 Negocial

```powershell
cd "C:\Sistemas\projeto-negocial-showcase\aplicacao-negocial"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 6.2 Gerencial

```powershell
cd "C:\Sistemas\projeto-negocial-showcase\aplicacao-gerencial"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
```

O `npm ci` instala Playwright e as ferramentas de desenvolvimento. Para executar
os testes completos de navegador posteriormente:

```powershell
npx playwright install chromium
```

## 7. Configurar variaveis de ambiente

Os arquivos `.env` sao locais e nao devem ser enviados ao repositorio. Os dois
sistemas devem apontar para a mesma `DATABASE_URL`.

### 7.1 Negocial

Na pasta `aplicacao-negocial`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Conteudo minimo para uma instalacao nova:

```env
DATABASE_URL=postgresql+psycopg://projeto_user:SENHA@127.0.0.1:5432/projeto_negocial
JWT_SECRET_KEY=CHAVE_ALEATORIA_COM_PELO_MENOS_48_CARACTERES
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
AUTH_COOKIE_NAME=negocial_token
ADMIN_USERNAME=admin.negocial
ADMIN_PASSWORD=SENHA_INICIAL_FORTE_COM_12_OU_MAIS_CARACTERES
```

Gere uma chave JWT segura com:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

`ADMIN_USERNAME` e `ADMIN_PASSWORD` sao usados somente se o schema Negocial ainda
nao tiver usuarios. Depois do primeiro login bem-sucedido, remova essas duas linhas
do `.env` ou deixe seus valores vazios.

Para escolher onde anexos de ferramentas serao armazenados, use a configuracao da
propria ferramenta no Gerencial. Como alternativa global do Negocial:

```env
FERRAMENTA_ATTACHMENTS_DIR=D:/Dados/ProjetoNegocial/anexos
```

### 7.2 Gerencial

Na pasta `aplicacao-gerencial`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Conteudo minimo para uma instalacao nova:

```env
DATABASE_URL=postgresql+psycopg://projeto_user:SENHA@127.0.0.1:5432/projeto_negocial
NEGOCIADORES_DATA_DIR=data
NEGOCIADORES_UI_DIR=ui
GERENCIAL_BOOTSTRAP_ADMIN_USERNAME=admin.gerencial
GERENCIAL_BOOTSTRAP_ADMIN_PASSWORD=SENHA_INICIAL_FORTE_COM_12_OU_MAIS_CARACTERES
```

O primeiro usuario do Gerencial recebe o perfil `superadmin`. Depois do primeiro
login, remova as duas variaveis `GERENCIAL_BOOTSTRAP_*` do `.env`.

Configuracoes opcionais estao documentadas em
[aplicacao-gerencial/.env.example](aplicacao-gerencial/.env.example).

## 8. Aplicar as migracoes

As aplicacoes aplicam migracoes ao iniciar, mas numa maquina nova e melhor valida-las
explicitamente antes do primeiro uso.

Negocial:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase\aplicacao-negocial"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Gerencial:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase\aplicacao-gerencial"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Nao use `alembic downgrade` em um banco com dados reais sem backup e validacao.

## 9. Certificado HTTPS do Gerencial

O Gerencial usa HTTPS quando encontra certificado e chave em `data/certs`. Gere-os
na maquina que executara o servidor:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase\aplicacao-gerencial"
.\.venv\Scripts\python.exe scripts\generate_https_cert.py
```

O certificado inclui `localhost`, o nome da maquina e seus enderecos IPv4 atuais.
Os inicializadores tambem verificam e regeneram o certificado quando necessario.

Para confiar no certificado no computador servidor, abra PowerShell como
Administrador e execute:

```powershell
Import-Certificate `
  -FilePath ".\data\certs\negociadores-local.crt" `
  -CertStoreLocation "Cert:\LocalMachine\Root"
```

Em cada computador cliente da intranet, instale uma copia do mesmo `.crt` em
`Autoridades de Certificacao Raiz Confiaveis`. Distribua apenas o arquivo `.crt`;
nunca distribua o arquivo `.key`.

Para um ambiente corporativo, prefira um certificado emitido pela autoridade
certificadora interna e configure:

```env
NEGOCIADORES_SSL_CERT=C:/certificados/gerencial.crt
NEGOCIADORES_SSL_KEY=C:/certificados/gerencial.key
```

## 10. Primeiro inicio

### Opcao A: iniciar os dois sistemas

Na raiz do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File .\iniciar-sistemas.ps1
```

O script:

- confirma que o PostgreSQL local esta ativo;
- encerra processos antigos nas portas 8765 e 8890;
- valida o certificado HTTPS;
- inicia os dois servidores em segundo plano;
- grava os PIDs e mostra os enderecos da rede;
- executa health checks.

Esse inicializador pressupoe PostgreSQL no computador local, porta 5432. Para um
banco remoto, inicie as aplicacoes separadamente conforme a opcao B.

### Opcao B: iniciar separadamente

Negocial:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase\aplicacao-negocial"
.\iniciar_negocial.ps1
```

Gerencial, em outro PowerShell:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase\aplicacao-gerencial"
.\iniciar_programa.ps1
```

As janelas devem permanecer abertas nessa modalidade. Use `Ctrl+C` para parar.

### Primeiro acesso

Abra:

- Negocial: [http://127.0.0.1:8890](http://127.0.0.1:8890)
- Gerencial: [https://127.0.0.1:8765](https://127.0.0.1:8765)

Entre com os usuarios de bootstrap configurados nos respectivos `.env`. Depois:

1. altere ou proteja as credenciais administrativas;
2. remova as senhas de bootstrap dos arquivos `.env`;
3. cadastre carteiras, negociadores e permissoes pelo Gerencial;
4. confirme o acesso de um negociador no Negocial.

## 11. Validacao final

Health checks:

```powershell
curl.exe -k https://127.0.0.1:8765/api/health/ready
curl.exe http://127.0.0.1:8890/api/health/ready
```

As duas respostas devem conter `"status":"ready"`.

Teste integrado sem login:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase"
.\aplicacao-gerencial\.venv\Scripts\python.exe .\scripts\smoke_systems.py
```

Teste integrado autenticado:

```powershell
$env:GERENCIAL_SMOKE_USERNAME="usuario"
$env:GERENCIAL_SMOKE_PASSWORD="senha"
$env:NEGOCIAL_SMOKE_USERNAME="usuario"
$env:NEGOCIAL_SMOKE_PASSWORD="senha"
.\aplicacao-gerencial\.venv\Scripts\python.exe .\scripts\smoke_systems.py
```

Para limpar as senhas da sessao atual do PowerShell:

```powershell
Remove-Item Env:GERENCIAL_SMOKE_USERNAME, Env:GERENCIAL_SMOKE_PASSWORD,
  Env:NEGOCIAL_SMOKE_USERNAME, Env:NEGOCIAL_SMOKE_PASSWORD -ErrorAction SilentlyContinue
```

## 12. Acesso pela rede interna

Descubra o nome e o IPv4 do servidor:

```powershell
hostname
ipconfig
```

Em outro computador da mesma rede, use:

```text
https://NOME-DA-MAQUINA:8765
http://NOME-DA-MAQUINA:8890
```

Se o DNS local nao resolver o nome, teste pelo IPv4. Para liberar as portas, abra
PowerShell como Administrador no servidor:

```powershell
New-NetFirewallRule -DisplayName "Projeto Negocial - Gerencial 8765" `
  -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private,Domain

New-NetFirewallRule -DisplayName "Projeto Negocial - Negocial 8890" `
  -Direction Inbound -Protocol TCP -LocalPort 8890 -Action Allow -Profile Private,Domain
```

Nao exponha essas portas diretamente na internet. Para acesso externo, use VPN e
um proxy reverso administrado pela equipe de infraestrutura.

## 13. Inicializacao automatica

Depois de validar o inicio manual, instale a tarefa agendada no computador servidor:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase"
powershell -ExecutionPolicy Bypass -File .\instalar-inicializacao.ps1
```

A tarefa `Projeto Negocial - Servidores` iniciara os sistemas no login do usuario.
Para remover:

```powershell
Unregister-ScheduledTask -TaskName "Projeto Negocial - Servidores" -Confirm:$false
```

## 14. Testes do codigo

Validacao completa sem navegador:

```powershell
cd "C:\Sistemas\projeto-negocial-showcase"
powershell -ExecutionPolicy Bypass -File .\scripts\check-project.ps1
```

Com Playwright:

```powershell
$env:GERENCIAL_E2E_USERNAME="usuario_de_teste"
$env:GERENCIAL_E2E_PASSWORD="senha_de_teste"
powershell -ExecutionPolicy Bypass -File .\scripts\check-project.ps1 -E2E
```

Os testes unitarios usam bancos temporarios quando previsto. Ainda assim, nunca
aponte scripts de importacao, restore ou carga para o banco real sem revisar seus
parametros.

## 15. Dados, anexos e integracoes

- Dados transacionais ficam no PostgreSQL.
- Configuracoes locais, certificados e arquivos auxiliares ficam em
  `aplicacao-gerencial/data`.
- O destino de anexos de ferramentas pode ser configurado pelo Gerencial.
- A origem dos arquivos de Defasagem pode ser escolhida nas configuracoes da tela.
- Pareceres, Protocolo e Colchao podem depender de arquivos ou diretorios externos
  definidos no Gerencial.
- Use caminhos absolutos locais ou UNC estaveis, como `\\servidor\setor\arquivo.xlsx`.
- A conta do Windows que executa o servidor precisa de leitura e escrita nos
  diretorios configurados.

Ao trocar de maquina, revise todos os caminhos externos. Letras como `Z:` podem nao
existir para tarefas agendadas; caminhos UNC sao mais confiaveis nesse caso.

## 16. Backup e mudanca de maquina

O Gerencial agenda backups PostgreSQL e aplica politicas de retencao, mas a copia
de seguranca deve sair do mesmo disco do servidor.

Backup manual:

```powershell
pg_dump -h 127.0.0.1 -U projeto_user -Fc `
  -f "D:\Backups\projeto_negocial.dump" projeto_negocial
```

Restauracao em banco vazio:

```powershell
createdb -h 127.0.0.1 -U postgres -O projeto_user projeto_negocial
pg_restore -h 127.0.0.1 -U projeto_user -d projeto_negocial --clean --if-exists `
  "D:\Backups\projeto_negocial.dump"
```

Antes de migrar para outra maquina:

1. pare os dois sistemas;
2. gere e valide um dump PostgreSQL;
3. copie o codigo sem reutilizar os `.venv`;
4. copie anexos e arquivos externos preservando permissoes;
5. restaure o banco;
6. recrie os ambientes Python e o certificado;
7. revise os `.env` e caminhos configurados;
8. execute migracoes e health checks;
9. somente entao libere a nova maquina aos usuarios.

Consulte tambem
[disaster-recovery.md](aplicacao-gerencial/docs/disaster-recovery.md).

## 17. Logs e diagnostico

Arquivos principais quando os sistemas sao iniciados pela raiz:

```text
aplicacao-gerencial/gerencial-postgres.out.log
aplicacao-gerencial/gerencial-postgres.err.log
aplicacao-negocial/negocial-postgres.out.log
aplicacao-negocial/negocial-postgres.err.log
```

Comandos uteis:

```powershell
Get-Content .\aplicacao-gerencial\gerencial-postgres.err.log -Tail 100
Get-Content .\aplicacao-negocial\negocial-postgres.err.log -Tail 100
Get-NetTCPConnection -LocalPort 8765,8890 -State Listen
Get-Service -Name "postgresql*"
```

Cada requisicao recebe um `X-Request-ID`, tambem presente nos logs estruturados.

### Problemas comuns

| Sintoma | Verificacao |
|---|---|
| `python` nao reconhecido | Reinstale Python marcando `Add Python to PATH` ou use o caminho completo. |
| `.venv` nao encontrado | Recrie o ambiente virtual na pasta da aplicacao correspondente. |
| Falha ao conectar no banco | Confira servico PostgreSQL, porta, usuario, senha e `DATABASE_URL` nos dois `.env`. |
| Banco sem usuarios | Preencha as variaveis de bootstrap, inicie uma vez e depois remova-as. |
| Porta em uso | Localize o PID com `Get-NetTCPConnection` e confirme qual programa esta usando a porta. |
| Gerencial abre com alerta HTTPS | Instale o `.crt` como raiz confiavel e acesse por um nome/IP incluido no certificado. |
| Nome da maquina nao abre | Teste pelo IPv4, confira firewall, perfil da rede e resolucao DNS. |
| Planilha nao atualiza | Confira caminho, permissao da conta do servidor, arquivo bloqueado e Excel instalado. |
| Migracao falha | Nao apague tabelas; preserve o log, confira `alembic current` e restaure um backup se necessario. |

## 18. Modo SQLite para desenvolvimento isolado

SQLite e util para testes locais sem PostgreSQL, mas nao representa o ambiente
completo multiusuario e nao deve ser usado como servidor de producao.

Negocial `.env`:

```env
DATABASE_URL=sqlite:///database/negocial.sqlite3
ADMIN_USERNAME=admin.local
ADMIN_PASSWORD=SENHA_LOCAL_FORTE_COM_12_OU_MAIS_CARACTERES
```

Gerencial `.env`:

```env
DATABASE_URL=sqlite:///data/app.sqlite3
GERENCIAL_BOOTSTRAP_ADMIN_USERNAME=admin.local
GERENCIAL_BOOTSTRAP_ADMIN_PASSWORD=SENHA_LOCAL_FORTE_COM_12_OU_MAIS_CARACTERES
```

Nesse modo, cada aplicacao usa seu proprio arquivo e nao ha compartilhamento
completo de dados entre os sistemas. Para validar a solucao real, use PostgreSQL.

## 19. Documentacao complementar

- [Operacao diaria](OPERACAO.md)
- [Arquitetura do Gerencial](aplicacao-gerencial/docs/architecture.md)
- [Modelo do banco](aplicacao-gerencial/docs/database-model.md)
- [Observabilidade](aplicacao-gerencial/docs/database-observability.md)
- [Recuperacao de desastre](aplicacao-gerencial/docs/disaster-recovery.md)
- [Ferramentas negociais](aplicacao-gerencial/docs/ferramentas-negociais.md)
- [README do Negocial](aplicacao-negocial/README.md)
- [README do Gerencial](aplicacao-gerencial/README.md)

## Checklist de entrega

- [ ] Python, PostgreSQL e Node instalados.
- [ ] Banco e usuario PostgreSQL criados.
- [ ] `.venv` criado nas duas aplicacoes.
- [ ] Dependencias Python e Node instaladas.
- [ ] `.env` configurado nas duas aplicacoes.
- [ ] Migracoes Negocial e Gerencial em `head`.
- [ ] Certificado HTTPS gerado e confiavel.
- [ ] Negocial respondendo na porta 8890.
- [ ] Gerencial respondendo na porta 8765.
- [ ] Primeiro login realizado nos dois sistemas.
- [ ] Credenciais de bootstrap removidas dos `.env`.
- [ ] Health checks e smoke test aprovados.
- [ ] Firewall e DNS validados, quando houver acesso em rede.
- [ ] Backup inicial criado e restauracao ensaiada.
