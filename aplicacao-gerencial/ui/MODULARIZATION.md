# Modularizacao do Frontend

Objetivo: reduzir gradualmente o tamanho do `app.js`, separando responsabilidades sem quebrar a aplicacao funcional.

## Status

```text
ui/
  app.js                         OK
  core/
    api.js                       OK
    state.js                     OK
    dom.js                       OK
    html.js                      OK
    format.js                    OK
    loading.js                   OK
    session.js                   OK
    toast.js                     OK
  features/
    spreadsheetGrid.js           OK
    spreadsheetGridCore.js       OK
    spreadsheetGridEditing.js    OK
    changeDiff.js                OK
    parecerActions.js            OK
    mainHubCards.js              OK
    mainHubView.js               OK
    parecerData.js               OK
    parecerView.js               OK
    protocolo.js                 OK
    protocoloData.js             OK
    protocoloView.js             OK
    parecer.js                   OK
    negociadores.js              OK
    negociadoresCrud.js          OK
    negociadoresEvents.js        OK
    negociadoresGrid.js          OK
    overview.js                  OK
    overviewView.js              OK
    mainHub.js                   OK
    notifications.js             OK
    negociadorTimeline.js       OK
    timelineData.js              OK
  layout/
    actions.js                   OK
    dialogs.js                   OK
    navigation.js                OK
    sidebar.js                   OK
    profile.js                   OK
    theme.js                     OK
    toolSwitcher.js              OK
    visibility.js                OK
  templates/
    shell/dialogs.html           OK
    groups/empty.html            OK
    modules/backoffice/index.html OK
```

## Ordem Recomendada

1. `features/protocolo.js`
   - Ja possui fluxo proprio: configuracao, dashboard, cards, tabela, status e edicao de celula.
   - Usa `spreadsheetGrid.js`, entao e o proximo corte natural.
   - Status: concluido.

2. `core/api.js`, `core/dom.js`, `core/toast.js`
   - Extrair utilitarios compartilhados antes de separar muitos features.
   - Reduz acoplamento e evita duplicacao.
   - Status: concluido.

3. `features/parecer.js`
   - Fluxo independente com dashboard, pendentes, planilha completa e Power Query.
   - Status: concluido.

4. `features/overview.js`, `features/mainHub.js`, `features/notifications.js`
   - Areas conectadas entre si; melhor separar depois dos utilitarios centrais.

5. `features/negociadores.js` e `features/negociadorTimeline.js`
   - Dependem bastante do estado principal e da renderizacao da planilha individual.
   - Status negociadores: concluido.
   - Status timeline: concluido.

6. `layout/sidebar.js`, `layout/profile.js`, `layout/theme.js`
   - Refatoracao de baixo risco, boa para fechamento quando os features maiores ja estiverem isolados.
   - Status: concluido.

## Regra de Trabalho

- Fazer uma extracao por vez.
- Validar com `node --check`.
- Confirmar que os arquivos novos sao servidos pela aplicacao.
- Evitar mudar comportamento enquanto estiver modularizando.
