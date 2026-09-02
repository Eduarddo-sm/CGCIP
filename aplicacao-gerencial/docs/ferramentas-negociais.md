# Ferramentas negociais dinamicas

## Objetivo

Permitir que administradores criem ferramentas operacionais no Gerencial sem
criar uma tabela ou uma pagina nova para cada processo. A definicao publicada
passa a ser exibida automaticamente no Negocial para as carteiras e usuarios
autorizados.

## Fluxo

1. O administrador acessa `Configuracao > Ferramentas`.
2. Cria a ferramenta, seus campos, status, transicoes e permissoes.
3. Salva o rascunho e publica a versao.
4. O Negocial descobre a nova ferramenta pela API e monta formulario e tabela.
5. Cada registro preserva a versao de schema usada em sua criacao.
6. O Gerencial consulta os registros, comenta, executa transicoes e gera XLSX.
7. Registros em status nao final aparecem nas notificacoes gerenciais.

## Cadastro com status opcional

Ferramentas do tipo `CADASTRO` podem desativar o controle de status. Nesse
modo, o sistema utiliza internamente o estado final `REGISTRADO`, que nao
aparece nas telas, nos filtros, nos relatorios ou nas notificacoes.

Quando o controle de status esta ativo, o administrador pode permitir que o
negociador escolha o status inicial no formulario. Ferramentas do tipo
`SOLICITACAO` sempre exigem um status inicial e mantem o workflow obrigatorio.

## Modelo de dados

- `ferramentas`: identidade estavel da ferramenta.
- `ferramenta_versoes`: rascunhos, versoes publicadas e arquivadas.
- `ferramenta_campos`: schema dos formularios e tabelas.
- `ferramenta_status`: estados disponiveis e indicador de estado final.
- `ferramenta_transicoes`: workflow e exigencia de justificativa.
- `ferramenta_permissoes`: acesso por carteira ou excecao por usuario.
- `ferramenta_registros`: dados operacionais em JSONB com metadados indexados.
- `ferramenta_eventos`: trilha imutavel de criacao, edicao e transicao.
- `ferramenta_comentarios`: comunicacao vinculada ao registro.
- `ferramenta_anexos`: metadados para futura integracao de arquivos.

## Regras de seguranca

- Apenas administradores gerenciais editam e publicam definicoes.
- O Negocial valida permissao por usuario antes da permissao da carteira.
- Campos desconhecidos sao rejeitados.
- Campos obrigatorios, tipos, opcoes e condicionais sao validados no backend.
- Transicoes fora do workflow publicado sao rejeitadas.
- Justificativas obrigatorias sao validadas no backend.
- IDs gerenciais nao sao gravados como IDs negociais; o vinculo ocorre pelo
  username quando houver usuario correspondente.

## Versionamento

Uma ferramenta possui apenas uma versao publicada e, opcionalmente, um
rascunho. Publicar arquiva a versao anterior. Registros existentes continuam
apontando para a versao original, evitando reinterpretacao incorreta de dados
historicos.

## Operacao e relatorios

O botao `Registros` abre a central operacional com:

- busca global;
- filtros por status, carteira e negociador;
- detalhes completos;
- transicoes permitidas;
- justificativa;
- comentarios;
- historico;
- exportacao XLSX usando os mesmos filtros.

## Cache e atualizacao

Alteracoes incrementam `operational_versions` nos escopos `ferramentas` e
`ferramenta:{slug/id}`. O Negocial usa essas versoes para atualizar definicoes
e registros sem recarregar toda a aplicacao.
