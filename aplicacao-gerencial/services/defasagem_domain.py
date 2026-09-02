from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from io import BytesIO
from typing import Any, Iterable

import pandas as pd
from openpyxl.styles import Font, PatternFill


logger = logging.getLogger(__name__)

REQUIRED_EXCEL_COLUMNS = [
    "carteira",
    "contrato",
    "nome_cliente",
    "fase",
    "uf",
    "nome_op",
    "gecor",
]

GARANTIA_COLUMN_CANDIDATES = [
    "tipo_garantia",
    "tipo_de_garantia",
    "garantia",
    "garantias",
    "tipo",
    "gatilho",
]

GATILHO_COLUMN_CANDIDATES = [
    "gatilho",
    "tipo_gatilho",
    "tipo_de_gatilho",
    "gatilhos",
    "tipo_garantia",
    "tipo_de_garantia",
]

CLIENT_LINK_COLUMN_CANDIDATES = [
    "nome_cliente",
    "nome",
    "cliente",
]

FAIXA_ORDER = [
    "Até 3 meses",
    "Até 6 meses",
    "Até 1 ano",
    "Após 1 ano",
    "Sem acionamento",
]

SPECIAL_STATUS_ORDER = [
    "Negociação",
    "Possível negócio",
    "Desinteresse da Parte",
]

EXPORT_COLUMNS = [
    "contrato",
    "contrato_bd",
    "cliente",
    "carteira",
    "fase",
    "uf",
    "nome_op",
    "gecor",
    "ultimo_acionamento",
    "data_ultimo_acionamento",
    "hora_ultimo_acionamento",
    "operador",
    "dias_sem_acionamento",
    "faixa_defasagem",
    "semaforo",
    "situacao_especial",
    "alerta_oportunidade",
    "prioridade_fila",
    "gatilhos",
    "quantidade_gatilhos",
    "garantias",
    "quantidade_garantias",
    "total_acionamentos",
    "observacao_ultimo_acionamento",
]


def normalize_column_name(value: Any) -> str:
    text_value = str(value).strip().lower()
    text_value = unicodedata.normalize("NFKD", text_value)
    text_value = text_value.encode("ascii", "ignore").decode("ascii")
    text_value = re.sub(r"[^a-z0-9]+", "_", text_value)
    return text_value.strip("_")


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text_value = str(value).strip().upper()
    text_value = unicodedata.normalize("NFKD", text_value)
    return text_value.encode("ascii", "ignore").decode("ascii")


def normalize_name_key(value: Any) -> str:
    text_value = normalize_text(value)
    text_value = re.sub(r"\s+", " ", text_value)
    return text_value.strip()


def clean_string_series(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip()


def clean_code_series(series: pd.Series) -> pd.Series:
    return clean_string_series(series).str.replace(r"\.0+$", "", regex=True)


def normalize_contract_key(value: Any) -> str:
    if pd.isna(value):
        return ""

    text_value = str(value).strip()
    if re.fullmatch(r"\d+\.0+", text_value):
        text_value = text_value.split(".", 1)[0]

    text_value = re.sub(r"\s+", "", text_value)
    if not text_value or text_value.lower() == "nan":
        return ""

    without_leading_zeros = text_value.lstrip("0")
    return without_leading_zeros or "0"


def _normalize_contract_keys(series: pd.Series) -> pd.Series:
    return series.map(normalize_contract_key).astype("string")


def _normalize_excluded_operators(values: Iterable[str] | None) -> set[str]:
    if not values:
        return set()
    return {normalize_text(value) for value in values if normalize_text(value)}


def read_contracts_excel(
    file_or_path: Any,
    excluded_operators: Iterable[str] | None = ("adrianof",),
) -> pd.DataFrame:
    df = pd.read_excel(file_or_path, engine="openpyxl", dtype={"contrato": "string"})
    df.columns = [normalize_column_name(column) for column in df.columns]

    missing_columns = [column for column in REQUIRED_EXCEL_COLUMNS if column not in df.columns]
    if missing_columns:
        expected = ", ".join(REQUIRED_EXCEL_COLUMNS)
        missing = ", ".join(missing_columns)
        raise ValueError(f"Excel invalido. Esperado: {expected}. Ausente: {missing}.")

    df = df[REQUIRED_EXCEL_COLUMNS].copy()
    for column in REQUIRED_EXCEL_COLUMNS:
        df[column] = clean_string_series(df[column])
    df["gecor"] = clean_code_series(df["gecor"])

    df["contrato_key"] = _normalize_contract_keys(df["contrato"])
    df["cliente_key"] = df["nome_cliente"].map(normalize_name_key).astype("string")
    df = df[df["contrato_key"].ne("")]

    excluded = _normalize_excluded_operators(excluded_operators)
    if excluded:
        df = df[~df["nome_op"].map(normalize_text).isin(excluded)]

    df = df.drop_duplicates(subset=["contrato_key"], keep="last").reset_index(drop=True)
    return df


def read_guarantees_excel(file_or_path: Any | None) -> pd.DataFrame:
    return read_category_excel(
        file_or_path=file_or_path,
        category_column="tipo_garantia",
        category_candidates=GARANTIA_COLUMN_CANDIDATES,
        empty_label="Sem garantia informada",
        file_label="garantias",
    )


def read_triggers_excel(file_or_path: Any | None) -> pd.DataFrame:
    return read_category_excel(
        file_or_path=file_or_path,
        category_column="gatilho",
        category_candidates=GATILHO_COLUMN_CANDIDATES,
        empty_label="Sem gatilho informado",
        file_label="gatilhos",
    )


def read_category_excel(
    file_or_path: Any | None,
    category_column: str,
    category_candidates: list[str],
    empty_label: str,
    file_label: str,
) -> pd.DataFrame:
    base_columns = [
        "identificador",
        "contrato",
        "contrato_key",
        "cliente_nome",
        "cliente_key",
        "entidade_key",
        category_column,
    ]
    if file_or_path is None:
        return pd.DataFrame(columns=base_columns)

    df = pd.read_excel(file_or_path, engine="openpyxl", dtype={"contrato": "string"})
    df.columns = [normalize_column_name(column) for column in df.columns]

    value_column = next(
        (column for column in category_candidates if column in df.columns),
        None,
    )
    if value_column is None:
        expected = ", ".join(category_candidates)
        raise ValueError(
            f"Excel de {file_label} invalido. Informe uma coluna de categoria: "
            f"{expected}."
        )

    identifier_column = "contrato" if "contrato" in df.columns else next(
        (column for column in CLIENT_LINK_COLUMN_CANDIDATES if column in df.columns),
        None,
    )
    if identifier_column is None:
        expected = "contrato, " + ", ".join(CLIENT_LINK_COLUMN_CANDIDATES)
        raise ValueError(
            f"Excel de {file_label} invalido. Informe uma coluna para vinculo: "
            f"{expected}."
        )

    df = df[[identifier_column, value_column]].rename(
        columns={
            identifier_column: "identificador",
            value_column: category_column,
        }
    )
    df["identificador"] = clean_string_series(df["identificador"])
    df[category_column] = clean_string_series(df[category_column])

    if identifier_column == "contrato":
        df["contrato"] = df["identificador"]
        df["contrato_key"] = _normalize_contract_keys(df["identificador"])
        df["cliente_nome"] = ""
        df["cliente_key"] = ""
        df = df[df["contrato_key"].ne("")]
    else:
        df["contrato"] = ""
        df["contrato_key"] = ""
        df["cliente_nome"] = df["identificador"]
        df["cliente_key"] = df["identificador"].map(normalize_name_key).astype("string")
        df = df[df["cliente_key"].ne("")]

    df[category_column] = df[category_column].replace("", empty_label)
    df[category_column] = df[category_column].str.split(r"[;,\n|/]+")
    df = df.explode(category_column)
    df[category_column] = clean_string_series(df[category_column]).replace(
        "",
        empty_label,
    )
    df["entidade_key"] = df["contrato_key"].mask(
        df["contrato_key"].eq(""),
        df["cliente_key"],
    )

    return df.drop_duplicates(subset=["entidade_key", category_column]).reset_index(
        drop=True
    )


def prepare_contract_keys(contracts_df: pd.DataFrame) -> tuple[str, ...]:
    if contracts_df.empty:
        return tuple()
    if "contrato_key" in contracts_df:
        keys = clean_string_series(contracts_df["contrato_key"])
    else:
        keys = _normalize_contract_keys(contracts_df["contrato"])
    return tuple(keys[keys.ne("")].dropna().unique())


def classify_defasagem(dias_sem_acionamento: pd.Series) -> pd.Series:
    dias = dias_sem_acionamento.astype("Float64")
    faixa = pd.Series("Após 1 ano", index=dias.index, dtype="string")
    faixa = faixa.mask(dias <= 365, "Até 1 ano")
    faixa = faixa.mask(dias <= 180, "Até 6 meses")
    faixa = faixa.mask(dias <= 90, "Até 3 meses")
    faixa = faixa.mask(dias.isna(), "Sem acionamento")
    return faixa


def classify_semaforo(dias_sem_acionamento: pd.Series) -> pd.Series:
    dias = dias_sem_acionamento.astype("Float64")
    semaforo = pd.Series("Vermelho", index=dias.index, dtype="string")
    semaforo = semaforo.mask(dias <= 180, "Laranja")
    semaforo = semaforo.mask(dias <= 90, "Amarelo")
    semaforo = semaforo.mask(dias <= 30, "Verde")
    semaforo = semaforo.mask(dias.isna(), "Sem acionamento")
    return semaforo


def _latest_actions_for_cards(
    manual_actions_df: pd.DataFrame,
    card_actions_df: pd.DataFrame | None,
) -> pd.DataFrame:
    frames = []
    for actions_df in [manual_actions_df, card_actions_df]:
        if actions_df is None or actions_df.empty:
            continue

        actions = actions_df.copy()
        if "contrato_key_db" in actions:
            actions["contrato_key"] = clean_string_series(actions["contrato_key_db"])
        else:
            actions["contrato_key"] = _normalize_contract_keys(
                actions.get("contrato", pd.Series(dtype="string"))
            )

        actions = actions[actions["contrato_key"].ne("")]
        if actions.empty:
            continue

        actions["data_ultimo_acionamento_cards"] = pd.to_datetime(
            actions.get("data_ultimo_acionamento"), errors="coerce"
        )
        actions["hora_ultimo_acionamento_cards"] = clean_string_series(
            actions.get("hora_ultimo_acionamento", pd.Series(dtype="string"))
        )
        actions["ultimo_acionamento_cards"] = clean_string_series(
            actions.get("ultimo_acionamento", pd.Series(dtype="string"))
        )
        actions["_hora_cards_sort"] = pd.to_timedelta(
            actions["hora_ultimo_acionamento_cards"], errors="coerce"
        )
        frames.append(actions[[
            "contrato_key", "ultimo_acionamento_cards",
            "data_ultimo_acionamento_cards", "hora_ultimo_acionamento_cards",
            "_hora_cards_sort",
        ]])

    if not frames:
        return pd.DataFrame(columns=[
            "contrato_key", "ultimo_acionamento_cards",
            "data_ultimo_acionamento_cards", "hora_ultimo_acionamento_cards",
        ])

    cards = pd.concat(frames, ignore_index=True).sort_values(
        by=["contrato_key", "data_ultimo_acionamento_cards", "_hora_cards_sort"],
        ascending=[True, False, False],
        na_position="last",
    )
    return (
        cards.drop_duplicates(subset=["contrato_key"], keep="first")
        .drop(columns=["_hora_cards_sort"])
        .reset_index(drop=True)
    )


def enrich_contracts(
    contracts_df: pd.DataFrame,
    last_actions_df: pd.DataFrame,
    settings: Any,
    card_actions_df: pd.DataFrame | None = None,
    today: date | None = None,
) -> pd.DataFrame:
    today_ts = pd.Timestamp(today or date.today()).normalize()

    contracts = contracts_df.copy()
    if "contrato_key" not in contracts:
        contracts["contrato_key"] = _normalize_contract_keys(contracts["contrato"])

    actions = last_actions_df.copy()
    if actions.empty:
        actions = pd.DataFrame(
            columns=[
                "carteira_db",
                "contrato",
                "contrato_key_db",
                "nome_cliente_db",
                "ultimo_acionamento",
                "data_ultimo_acionamento",
                "hora_ultimo_acionamento",
                "observacao_ultimo_acionamento",
                "operador",
                "total_acionamentos",
            ]
        )

    if "contrato_key_db" in actions:
        actions["contrato_key"] = clean_string_series(actions["contrato_key_db"])
    else:
        actions["contrato_key"] = _normalize_contract_keys(
            actions.get("contrato", pd.Series(dtype="string"))
        )

    merged = contracts.merge(
        actions.drop(columns=["contrato_key_db"], errors="ignore"),
        on="contrato_key",
        how="left",
        suffixes=("", "_db_action"),
    )

    merged["contrato_bd"] = clean_string_series(
        merged.get("contrato_db_action", pd.Series(dtype="string"))
    )
    merged = merged.drop(columns=["contrato_db_action"], errors="ignore")

    for column in ["carteira", "fase", "uf", "nome_op", "gecor"]:
        merged[column] = clean_string_series(merged[column])

    if "carteira_db" in merged:
        merged["carteira"] = merged["carteira"].mask(
            merged["carteira"].eq(""),
            clean_string_series(merged["carteira_db"]),
        )

    merged["cliente"] = clean_string_series(merged["nome_cliente"])
    if "nome_cliente_db" in merged:
        merged["cliente"] = merged["cliente"].mask(
            merged["cliente"].eq(""),
            clean_string_series(merged["nome_cliente_db"]),
        )
    merged["cliente_key"] = merged["cliente"].map(normalize_name_key).astype("string")

    merged["ultimo_acionamento"] = clean_string_series(
        merged.get("ultimo_acionamento", pd.Series(dtype="string"))
    ).replace("", "Sem acionamento")
    merged["operador"] = clean_string_series(
        merged.get("operador", pd.Series(dtype="string"))
    ).replace("", "Sem operador")
    merged["observacao_ultimo_acionamento"] = clean_string_series(
        merged.get("observacao_ultimo_acionamento", pd.Series(dtype="string"))
    )
    merged["hora_ultimo_acionamento"] = clean_string_series(
        merged.get("hora_ultimo_acionamento", pd.Series(dtype="string"))
    )

    merged["data_ultimo_acionamento"] = pd.to_datetime(
        merged.get("data_ultimo_acionamento"),
        errors="coerce",
    )
    dias = (today_ts - merged["data_ultimo_acionamento"].dt.normalize()).dt.days
    merged["dias_sem_acionamento"] = dias.astype("Int64")
    merged["faixa_defasagem"] = classify_defasagem(merged["dias_sem_acionamento"])
    merged["semaforo"] = classify_semaforo(merged["dias_sem_acionamento"])

    card_actions = _latest_actions_for_cards(last_actions_df, card_actions_df)
    if card_actions.empty:
        merged["ultimo_acionamento_cards"] = merged["ultimo_acionamento"]
        merged["data_ultimo_acionamento_cards"] = merged["data_ultimo_acionamento"]
        merged["hora_ultimo_acionamento_cards"] = merged["hora_ultimo_acionamento"]
    else:
        merged = merged.merge(card_actions, on="contrato_key", how="left")
        status_cards = clean_string_series(
            merged.get("ultimo_acionamento_cards", pd.Series(dtype="string"))
        )
        merged["ultimo_acionamento_cards"] = status_cards.mask(
            status_cards.eq(""), merged["ultimo_acionamento"]
        )
        hour_cards = clean_string_series(
            merged.get("hora_ultimo_acionamento_cards", pd.Series(dtype="string"))
        )
        merged["hora_ultimo_acionamento_cards"] = hour_cards.mask(
            hour_cards.eq(""), merged["hora_ultimo_acionamento"]
        )
        merged["data_ultimo_acionamento_cards"] = pd.to_datetime(
            merged.get("data_ultimo_acionamento_cards"), errors="coerce"
        ).fillna(merged["data_ultimo_acionamento"])

    card_days = (
        today_ts - merged["data_ultimo_acionamento_cards"].dt.normalize()
    ).dt.days
    merged["dias_sem_acionamento_cards"] = card_days.astype("Int64")
    merged["faixa_defasagem_cards"] = classify_defasagem(
        merged["dias_sem_acionamento_cards"]
    )

    status_norm = merged["ultimo_acionamento"].map(normalize_text)
    fase_norm = merged["fase"].map(normalize_text)
    dias_alerta = merged["dias_sem_acionamento"].astype("Float64")

    is_negociacao = status_norm.str.contains("NEGOCIACAO", na=False)
    is_possivel_negocio = status_norm.str.contains("POSSIVEL NEGOCIO", na=False)
    is_desinteresse = status_norm.str.contains("DESINTERESSE", na=False)
    is_localizado = status_norm.str.contains("LOCALIZADO", na=False)
    is_ativo = fase_norm.str.contains("ATIVO", na=False) & ~fase_norm.str.contains(
        "INATIVO", na=False
    )

    merged["is_negociacao"] = is_negociacao
    merged["is_possivel_negocio"] = is_possivel_negocio
    merged["is_desinteresse"] = is_desinteresse
    merged["negociacao_sem_retorno"] = is_negociacao & (
        dias_alerta >= settings.negociacao_alert_dias
    )
    merged["possivel_negocio_sem_retorno"] = is_possivel_negocio & (
        dias_alerta >= settings.possivel_negocio_alert_dias
    )
    merged["desinteresse_sem_retorno"] = is_desinteresse & (
        dias_alerta >= settings.desinteresse_alert_dias
    )

    situacao = pd.Series("Demais", index=merged.index, dtype="string")
    situacao = situacao.mask(is_desinteresse, "Desinteresse da Parte")
    situacao = situacao.mask(is_possivel_negocio, "Possível negócio")
    situacao = situacao.mask(is_negociacao, "Negociação")
    merged["situacao_especial"] = situacao

    alerta = pd.Series("Sem alerta", index=merged.index, dtype="string")
    alerta = alerta.mask(dias_alerta.isna(), "Contrato sem histórico de acionamento")
    alerta = alerta.mask(
        is_ativo & (dias_alerta >= settings.critico_dias),
        "Contrato ativo há muito tempo sem retorno",
    )
    alerta = alerta.mask(
        (dias_alerta >= settings.critico_dias) & alerta.eq("Sem alerta"),
        "Contrato esquecido",
    )
    alerta = alerta.mask(
        is_localizado & (dias_alerta >= settings.sem_retorno_dias),
        "Cliente localizado sem nova ação",
    )
    alerta = alerta.mask(
        merged["desinteresse_sem_retorno"],
        "Desinteresse da parte sem retorno há 3 meses",
    )
    alerta = alerta.mask(
        merged["possivel_negocio_sem_retorno"],
        "Possível negócio abandonado",
    )
    alerta = alerta.mask(
        merged["negociacao_sem_retorno"],
        "URGENTE - Cliente negociando sem retorno",
    )
    merged["alerta_oportunidade"] = alerta

    merged["sem_retorno"] = dias_alerta.isna() | (
        dias_alerta >= settings.sem_retorno_dias
    )
    merged["is_critico"] = (
        dias_alerta.isna()
        | (dias_alerta >= settings.critico_dias)
        | merged["negociacao_sem_retorno"]
        | merged["possivel_negocio_sem_retorno"]
        | merged["desinteresse_sem_retorno"]
    )

    merged["total_acionamentos"] = (
        pd.to_numeric(merged.get("total_acionamentos"), errors="coerce")
        .fillna(0)
        .astype("Int64")
    )

    return merged.sort_values(
        by=["is_critico", "dias_sem_acionamento"],
        ascending=[False, False],
        na_position="first",
    ).reset_index(drop=True)


def _count_faixa(
    df: pd.DataFrame,
    faixa: str,
    column: str = "faixa_defasagem",
) -> int:
    return int(df.get(column, pd.Series(dtype="string")).eq(faixa).sum())


def build_metrics(df: pd.DataFrame, use_card_defasagem: bool = False) -> dict[str, int]:
    faixa_column = (
        "faixa_defasagem_cards"
        if use_card_defasagem and "faixa_defasagem_cards" in df.columns
        else "faixa_defasagem"
    )
    return {
        "total_clientes": int(df.get("contrato_key", pd.Series(dtype="string")).nunique()),
        "faixa_ate_3_meses": _count_faixa(df, "Até 3 meses", faixa_column),
        "faixa_ate_6_meses": _count_faixa(df, "Até 6 meses", faixa_column),
        "faixa_ate_1_ano": _count_faixa(df, "Até 1 ano", faixa_column),
        "faixa_apos_1_ano": _count_faixa(df, "Após 1 ano", faixa_column),
        "sem_acionamento": int(
            df.get("data_ultimo_acionamento", pd.Series(dtype="datetime64[ns]")).isna().sum()
        ),
        "negociacao_sem_retorno": int(
            df.get("negociacao_sem_retorno", pd.Series(dtype="boolean")).fillna(False).sum()
        ),
        "possivel_negocio_sem_retorno": int(
            df.get("possivel_negocio_sem_retorno", pd.Series(dtype="boolean")).fillna(False).sum()
        ),
        "desinteresse_sem_retorno": int(
            df.get("desinteresse_sem_retorno", pd.Series(dtype="boolean")).fillna(False).sum()
        ),
        "negociacao_total": int(
            df.get("is_negociacao", pd.Series(dtype="boolean")).fillna(False).sum()
        ),
        "possivel_negocio_total": int(
            df.get("is_possivel_negocio", pd.Series(dtype="boolean")).fillna(False).sum()
        ),
        "desinteresse_total": int(
            df.get("is_desinteresse", pd.Series(dtype="boolean")).fillna(False).sum()
        ),
    }


def build_special_defasagem(df: pd.DataFrame) -> pd.DataFrame:
    source = df[df["situacao_especial"].isin(SPECIAL_STATUS_ORDER)].copy()
    if source.empty:
        return pd.DataFrame(columns=["situacao_especial", "faixa_defasagem", "quantidade"])

    grouped = (
        source.groupby(["situacao_especial", "faixa_defasagem"], dropna=False)["contrato_key"]
        .nunique()
        .reset_index(name="quantidade")
    )
    grouped["situacao_especial"] = pd.Categorical(
        grouped["situacao_especial"],
        categories=SPECIAL_STATUS_ORDER,
        ordered=True,
    )
    grouped["faixa_defasagem"] = pd.Categorical(
        grouped["faixa_defasagem"],
        categories=FAIXA_ORDER,
        ordered=True,
    )
    return grouped.sort_values(["situacao_especial", "faixa_defasagem"])


def build_guarantee_summary(
    guarantees_df: pd.DataFrame,
    contracts_df: pd.DataFrame,
) -> pd.DataFrame:
    return build_category_summary(
        category_df=guarantees_df,
        contracts_df=contracts_df,
        category_column="tipo_garantia",
    )


def build_trigger_summary(
    triggers_df: pd.DataFrame,
    contracts_df: pd.DataFrame,
) -> pd.DataFrame:
    return build_category_summary(
        category_df=triggers_df,
        contracts_df=contracts_df,
        category_column="gatilho",
    )


def attach_category_details(
    contracts_df: pd.DataFrame,
    guarantees_df: pd.DataFrame,
    triggers_df: pd.DataFrame,
) -> pd.DataFrame:
    """Attach category labels to each contract without duplicating contract rows."""
    result = contracts_df.copy()
    result = _attach_category_column(
        result,
        guarantees_df,
        category_column="tipo_garantia",
        output_column="garantias",
    )
    return _attach_category_column(
        result,
        triggers_df,
        category_column="gatilho",
        output_column="gatilhos",
    )


def _attach_category_column(
    contracts_df: pd.DataFrame,
    category_df: pd.DataFrame,
    category_column: str,
    output_column: str,
) -> pd.DataFrame:
    result = contracts_df.copy()
    count_column = f"quantidade_{output_column}"
    flag_column = f"tem_{output_column[:-1]}"

    if category_df.empty or category_column not in category_df:
        result[output_column] = ""
        result[count_column] = 0
        result[flag_column] = False
        return result

    def lookup(key_column: str) -> dict[str, tuple[str, ...]]:
        source = category_df[
            category_df.get(key_column, pd.Series("", index=category_df.index))
            .astype("string")
            .fillna("")
            .str.strip()
            .ne("")
        ]
        if source.empty:
            return {}
        return {
            str(key): tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
            for key, values in source.groupby(key_column)[category_column]
        }

    by_contract = lookup("contrato_key")
    by_client = lookup("cliente_key")
    contract_keys = result.get(
        "contrato_key",
        pd.Series("", index=result.index, dtype="string"),
    ).astype("string").fillna("")
    client_keys = result.get(
        "cliente_key",
        pd.Series("", index=result.index, dtype="string"),
    ).astype("string").fillna("")

    values: list[tuple[str, ...]] = []
    for contract_key, client_key in zip(contract_keys, client_keys):
        combined = set(by_contract.get(str(contract_key), ()))
        combined.update(by_client.get(str(client_key), ()))
        values.append(tuple(sorted(combined)))

    result[output_column] = [" | ".join(items) for items in values]
    result[count_column] = pd.Series([len(items) for items in values], index=result.index, dtype="Int64")
    result[flag_column] = result[count_column].gt(0)
    return result


def assign_priority_queue(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the operational queue order agreed with Backoffice."""
    result = df.copy()
    index = result.index
    action_date = pd.to_datetime(
        result.get("data_ultimo_acionamento", pd.Series(pd.NaT, index=index)),
        errors="coerce",
    )
    days = pd.to_numeric(
        result.get("dias_sem_acionamento", pd.Series(pd.NA, index=index)),
        errors="coerce",
    )
    negotiation = result.get(
        "negociacao_sem_retorno",
        pd.Series(False, index=index, dtype="boolean"),
    ).fillna(False)
    possible = result.get(
        "possivel_negocio_sem_retorno",
        pd.Series(False, index=index, dtype="boolean"),
    ).fillna(False)
    disinterest = result.get(
        "desinteresse_sem_retorno",
        pd.Series(False, index=index, dtype="boolean"),
    ).fillna(False)

    labels = pd.Series("Ate 3 meses", index=index, dtype="string")
    ranks = pd.Series(7, index=index, dtype="Int64")
    rules = [
        (days.gt(90) & days.le(180), "Ate 6 meses", 6),
        (days.gt(180) & days.le(365), "Ate 1 ano", 5),
        (days.gt(365), "Apos 1 ano", 4),
        (disinterest, "Desinteresse s/ retorno", 3),
        (possible, "Possivel negocio s/ retorno", 2),
        (negotiation, "Negociacao s/ retorno", 1),
        (action_date.isna(), "Sem acionamentos", 0),
    ]
    for mask, label, rank in rules:
        labels = labels.mask(mask, label)
        ranks = ranks.mask(mask, rank)

    result["prioridade_fila"] = labels
    result["_prioridade_ordem"] = ranks
    return result


def build_category_summary(
    category_df: pd.DataFrame,
    contracts_df: pd.DataFrame,
    category_column: str,
) -> pd.DataFrame:
    if category_df.empty or contracts_df.empty:
        return pd.DataFrame(columns=[category_column, "quantidade"])

    contract_keys = set(clean_string_series(contracts_df["contrato_key"]))
    cliente_source = contracts_df.get("cliente", contracts_df.get("nome_cliente", pd.Series(dtype="string")))
    cliente_keys = set(cliente_source.map(normalize_name_key).astype("string"))

    by_contract = category_df["contrato_key"].isin(contract_keys)
    by_client = category_df["cliente_key"].isin(cliente_keys)
    source = category_df[by_contract | by_client].copy()
    if source.empty:
        return pd.DataFrame(columns=[category_column, "quantidade"])

    source["entidade_key"] = source["contrato_key"].mask(
        source["contrato_key"].eq(""),
        source["cliente_key"],
    )

    return (
        source.groupby(category_column, dropna=False)["entidade_key"]
        .nunique()
        .reset_index(name="quantidade")
        .sort_values("quantidade", ascending=False)
    )


def filter_dataframe(df: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    filtered = df.copy()

    filter_columns = [
        "carteira",
        "fase",
        "nome_op",
        "uf",
        "gecor",
        "operador",
        "faixa_defasagem",
        "ultimo_acionamento",
        "situacao_especial",
    ]
    for column in filter_columns:
        values = filters.get(column)
        if values and column in filtered:
            filtered = filtered[filtered[column].isin(values)]

    operational_filter = str(filters.get("filtro_operacional") or "").strip().lower()
    operational_columns = {
        "desinteresse_sem_retorno": "desinteresse_sem_retorno",
        "negociacao_sem_retorno": "negociacao_sem_retorno",
        "clientes_criticos": "is_critico",
        "possivel_negocio_sem_retorno": "possivel_negocio_sem_retorno",
    }
    if operational_filter == "cliente_sem_acionamento":
        filtered = filtered[filtered.get("data_ultimo_acionamento", pd.Series(index=filtered.index, dtype="datetime64[ns]")).isna()]
    elif operational_filter in operational_columns:
        column = operational_columns[operational_filter]
        filtered = filtered[filtered.get(column, pd.Series(False, index=filtered.index, dtype="boolean")).fillna(False)]

    operator_without_response = str(filters.get("operador_sem_retorno") or "").strip()
    if operator_without_response:
        operator = filtered.get("operador", pd.Series("", index=filtered.index, dtype="string"))
        no_response = filtered.get("sem_retorno", pd.Series(False, index=filtered.index, dtype="boolean")).fillna(False)
        filtered = filtered[operator.eq(operator_without_response) & no_response]

    defasagem_type = str(filters.get("tipo_defasagem") or "").strip().lower()
    type_columns = {
        "negociacao": "is_negociacao",
        "possivel_negocio": "is_possivel_negocio",
        "desinteresse": "is_desinteresse",
    }
    if defasagem_type in type_columns:
        column = type_columns[defasagem_type]
        filtered = filtered[filtered.get(column, pd.Series(False, index=filtered.index, dtype="boolean")).fillna(False)]

    dias_range = filters.get("dias_sem_acionamento")
    if dias_range:
        min_days, max_days = dias_range
        dias = filtered["dias_sem_acionamento"].astype("Float64")
        filtered = filtered[dias.isna() | dias.between(min_days, max_days, inclusive="both")]

    search = normalize_text(filters.get("busca", ""))
    if search:
        searchable_columns = [
            "contrato",
            "cliente",
            "carteira",
            "nome_op",
            "uf",
            "gecor",
            "ultimo_acionamento",
            "operador",
        ]
        searchable = pd.Series("", index=filtered.index, dtype="string")
        for column in searchable_columns:
            if column in filtered:
                searchable = searchable + " " + filtered[column].astype(str)
        searchable = searchable.map(normalize_text)
        filtered = filtered[searchable.str.contains(search, na=False, regex=False)]

    return filtered.reset_index(drop=True)


def export_columns(df: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in EXPORT_COLUMNS if column in df.columns]
    return df[columns].copy()


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    export_df = export_columns(df)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="defasagem")
        worksheet = writer.sheets["defasagem"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        header_fill = PatternFill("solid", fgColor="1F2937")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font

        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(
                max(max_length + 2, 12),
                45,
            )

    output.seek(0)
    return output.getvalue()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return export_columns(df).to_csv(index=False, sep=";", encoding="utf-8-sig").encode(
        "utf-8-sig"
    )
