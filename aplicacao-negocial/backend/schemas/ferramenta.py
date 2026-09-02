from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


FieldType = Literal[
    "texto",
    "texto_longo",
    "numero",
    "moeda",
    "data",
    "select",
    "multiselect",
    "boolean",
    "usuario",
    "carteira",
    "arquivo",
]


class FerramentaCampoInput(BaseModel):
    chave: str = Field(min_length=1, max_length=120)
    nome: str = Field(min_length=1, max_length=160)
    tipo: FieldType = "texto"
    ordem: int = Field(default=0, ge=0)
    etapa: int = Field(default=1, ge=1, le=10)
    obrigatorio: bool = False
    somente_leitura: bool = False
    visivel_negocial: bool = True
    visivel_gerencial: bool = True
    opcoes: list[str] = Field(default_factory=list)
    validacao: dict[str, Any] = Field(default_factory=dict)
    condicao: dict[str, Any] = Field(default_factory=dict)
    valor_padrao: Any = None

    @field_validator("chave", mode="before")
    @classmethod
    def normalize_key(cls, value):
        import re
        import unicodedata

        text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
        text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").upper()
        if not text:
            raise ValueError("Chave do campo invalida.")
        return text

    @field_validator("opcoes", mode="before")
    @classmethod
    def normalize_options(cls, value):
        if isinstance(value, str):
            value = value.split(",")
        return list(dict.fromkeys(str(item).strip() for item in (value or []) if str(item).strip()))


class FerramentaStatusInput(BaseModel):
    codigo: str = Field(min_length=1, max_length=80)
    nome: str = Field(min_length=1, max_length=120)
    cor: str | None = Field(default=None, max_length=20)
    ordem: int = Field(default=0, ge=0)
    inicial: bool = False
    final: bool = False

    @field_validator("codigo", mode="before")
    @classmethod
    def normalize_code(cls, value):
        return FerramentaCampoInput.normalize_key(value)


class FerramentaTransicaoInput(BaseModel):
    origem_codigo: str = Field(min_length=1, max_length=80)
    destino_codigo: str = Field(min_length=1, max_length=80)
    nome: str = Field(min_length=1, max_length=120)
    exige_justificativa: bool = False
    permite_negociador: bool = False
    permite_gerencial: bool = True
    configuracao: dict[str, Any] = Field(default_factory=dict)

    @field_validator("origem_codigo", "destino_codigo", mode="before")
    @classmethod
    def normalize_status_code(cls, value):
        return FerramentaCampoInput.normalize_key(value)


class FerramentaPermissaoInput(BaseModel):
    user_id: int | None = None
    carteira: str | None = Field(default=None, max_length=80)
    pode_visualizar: bool = True
    pode_criar: bool = True
    pode_editar: bool = True
    pode_transicionar: bool = False
    pode_exportar: bool = False


class FerramentaDefinitionInput(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=120)
    descricao: str | None = Field(default=None, max_length=500)
    tipo: Literal["CADASTRO", "SOLICITACAO"] = "CADASTRO"
    icone: str | None = Field(default=None, max_length=80)
    cor: str | None = Field(default=None, max_length=20)
    configuracao: dict[str, Any] = Field(default_factory=dict)
    campos: list[FerramentaCampoInput] = Field(min_length=1)
    statuses: list[FerramentaStatusInput] = Field(default_factory=list)
    transicoes: list[FerramentaTransicaoInput] = Field(default_factory=list)
    permissoes: list[FerramentaPermissaoInput] = Field(default_factory=list)


class FerramentaRecordInput(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default=None, max_length=80)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_initial_status(cls, value):
        if value in (None, ""):
            return None
        return FerramentaCampoInput.normalize_key(value)


class FerramentaTransitionInput(BaseModel):
    status: str = Field(min_length=1, max_length=80)
    justificativa: str | None = Field(default=None, max_length=2000)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value):
        return FerramentaCampoInput.normalize_key(value)


class FerramentaCommentInput(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)
