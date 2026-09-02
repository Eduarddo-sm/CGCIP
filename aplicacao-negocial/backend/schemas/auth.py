from decimal import Decimal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    carteira: str | None
    meta_pagamento: float
    enabled_tools: list[str] = Field(default_factory=lambda: ["producao", "pareceres"])
    active: bool


class AuthResponse(BaseModel):
    user: UserResponse


class UserMetaUpdate(BaseModel):
    meta_pagamento: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
