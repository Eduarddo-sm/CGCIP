import { state } from "../core/state.js";
import { parecerPk, parecerValue } from "./parecerData.js";
import { protocoloValue } from "./protocoloData.js";

export function hubCards() {
  const overview = state.hub.overview.map((item) => ({
    id: item.id,
    source: "monitoramento",
    tag: "MONITORAMENTO",
    title: item.cliente || item.campo || "Alteracao nao lida",
    subtitle: item.campo,
    meta: `${item.usuario || "Responsavel"} \u2022 ${item.sheet || "Sheet"}`,
    date: item.dataHora,
    action: "MARCAR COMO LIDO",
    raw: item,
  }));
  const pareceres = state.hub.pareceres.map((row) => {
    const pk = parecerPk(row);
    return {
      id: `parecer:${pk}`,
      source: "parecer",
      tag: "PARECER",
      title: parecerValue(row, ["CLIENTE", "NOME CLIENTE", "NOME DO CLIENTE", "NOME"]) || "Cliente nao identificado",
      subtitle: parecerValue(row, ["MOTIVO"]) || "Parecer pendente",
      meta: `${parecerValue(row, ["OPERADOR", "NEGOCIADOR"]) || "Negociador nao informado"} \u2022 NPJ ${parecerValue(row, ["NPJ"]) || pk}`,
      date: "",
      action: "SOLICITADO",
      raw: row,
    };
  });
  const protocolos = state.hub.protocolos.map((row) => ({
    id: `protocolo:${row.__row_number}`,
    source: "protocolo",
    tag: "PROTOCOLO",
    title: protocoloValue(row, ["NOME"]) || "Cliente nao identificado",
    subtitle: protocoloValue(row, ["PROCESSO"]) || "Processo nao informado",
    meta: `${protocoloValue(row, ["CARTEIRA"]) || "Carteira nao informada"} \u2022 PJ ${protocoloValue(row, ["PJ"]) || "nao informado"}`,
    date: protocoloValue(row, ["DATA DE SOLICITAÇÃO", "DATA DE SOLICITACAO", "DATA DE SOLICITAÃ‡ÃƒO"]),
    action: "CONCLUIDO",
    raw: row,
  }));
  const ferramentas = (state.hub.ferramentas || []).map((row) => ({
    id: `ferramenta:${row.tool_id}:${row.id}`,
    source: "ferramenta",
    tag: String(row.ferramenta || "FERRAMENTA").toLocaleUpperCase("pt-BR"),
    title: row.titulo || "Registro sem titulo",
    subtitle: row.status_nome || row.status || "Pendente",
    meta: `${row.negociador || "Negociador nao informado"} \u2022 ${row.carteira || "Carteira nao informada"}`,
    date: row.updated_at,
    action: "ABRIR FERRAMENTA",
    raw: row,
  }));
  return [...overview, ...pareceres, ...protocolos, ...ferramentas].sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
}

export function findHubCard(cardId) {
  return hubCards().find((card) => card.id === cardId);
}
