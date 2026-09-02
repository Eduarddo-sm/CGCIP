from __future__ import annotations

from typing import Any

from backend.routes.analise import handle_get as handle_analise_get
from backend.routes.colchao import handle_get as handle_colchao_get
from backend.routes.colchao import handle_post as handle_colchao_post
from backend.routes.colchao import handle_put as handle_colchao_put
from backend.routes.configuracao import handle_get as handle_configuracao_get
from backend.routes.configuracao import handle_post as handle_configuracao_post
from backend.routes.monitoramento import handle_get as handle_monitoramento_get
from backend.routes.main_hub import handle_get as handle_main_hub_get
from backend.routes.parecer import handle_get as handle_parecer_get
from backend.routes.parecer import handle_post as handle_parecer_post
from backend.routes.parecer import handle_put as handle_parecer_put
from backend.routes.protocolo import handle_get as handle_protocolo_get
from backend.routes.protocolo import handle_post as handle_protocolo_post
from backend.routes.protocolo import handle_put as handle_protocolo_put


GET_HANDLERS = (
    handle_main_hub_get,
    handle_configuracao_get,
    handle_analise_get,
    handle_monitoramento_get,
    handle_parecer_get,
    handle_protocolo_get,
    handle_colchao_get,
)


def dispatch_get(handler: Any, state: Any, parsed: Any, user: dict) -> bool:
    return any(route(handler, state, parsed, user) for route in GET_HANDLERS)


POST_HANDLERS = (handle_configuracao_post, handle_parecer_post, handle_protocolo_post, handle_colchao_post)


def dispatch_post(handler: Any, state: Any, path: str, user: dict) -> bool:
    return any(route(handler, state, path, user) for route in POST_HANDLERS)


PUT_HANDLERS = (handle_parecer_put, handle_protocolo_put, handle_colchao_put)


def dispatch_put(handler: Any, state: Any, path: str, user: dict) -> bool:
    return any(route(handler, state, path, user) for route in PUT_HANDLERS)
