# Operacao do Projeto Negocial

## Enderecos

- Gerencial: `http://NOME-DO-SERVIDOR:8765`
- Negocial: `http://NOME-DO-SERVIDOR:8890`
- Prontidao: `/api/health/ready` em cada sistema.

Prefira o nome DNS do servidor ao IP. O DNS deve ser configurado no roteador ou no DNS interno para apontar um nome estavel ao computador servidor.

## Inicializacao

Use `iniciar-sistemas.ps1`. Para iniciar automaticamente no login do computador servidor, execute uma vez:

```powershell
powershell -ExecutionPolicy Bypass -File .\instalar-inicializacao.ps1
```

## Teste de fumaca

O teste sem credenciais verifica prontidao e conexao com o banco:

```powershell
python .\scripts\smoke_systems.py
```

Para testar login, sessao e leitura dos modulos principais:

```powershell
$env:GERENCIAL_SMOKE_USERNAME="usuario"
$env:GERENCIAL_SMOKE_PASSWORD="senha"
$env:NEGOCIAL_SMOKE_USERNAME="usuario"
$env:NEGOCIAL_SMOKE_PASSWORD="senha"
python .\scripts\smoke_systems.py
```

As senhas ficam apenas no processo atual e nao devem ser gravadas neste arquivo.

## Validacao do codigo

Instale as dependencias declaradas em `aplicacao-gerencial/requirements.txt` e
`aplicacao-negocial/requirements.txt`. Depois execute toda a validacao local com:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-project.ps1
```

Para incluir os fluxos completos de navegador com Playwright:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-project.ps1 -E2E
```

O mesmo comando confirma que o componente Excel Grid compartilhado esta sincronizado
entre as duas aplicacoes.

## Logs e rastreamento

Cada resposta possui `X-Request-ID`. Os logs JSON contêm o mesmo identificador, rota, status e duracao. Use-o para localizar uma operacao lenta ou com falha sem expor o corpo da requisicao.

## Backups

- O Gerencial agenda um backup PostgreSQL automatico a cada 24 horas.
- O primeiro backup ocorre cinco minutos apos iniciar o servidor.
- A politica de retencao cobre arquivos Excel e dumps PostgreSQL.
- O intervalo pode ser configurado por `NEGOCIADORES_BACKUP_INTERVAL_HOURS`.
- Teste restauracoes periodicamente em um banco separado; nunca valide restore diretamente no banco de producao.

## Recuperacao

1. Pare os dois sistemas.
2. Confirme o dump escolhido na tela de backups do Gerencial.
3. Crie um backup imediatamente antes do restore.
4. Restaure em ambiente de teste e execute `scripts/smoke_systems.py`.
5. Somente depois repita no ambiente de producao.

## Seguranca recomendada

- Trocar segredos e senhas padrao presentes nos arquivos `.env`.
- Manter PostgreSQL acessivel apenas pela rede interna e por usuarios especificos.
- Para HTTPS interno, instalar certificado emitido pela autoridade da empresa e configurar `NEGOCIADORES_SSL_CERT` e `NEGOCIADORES_SSL_KEY`.
- Limitar acesso ao computador servidor e manter Windows/PostgreSQL atualizados.
