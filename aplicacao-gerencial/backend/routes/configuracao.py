from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs
import re


AUDIT_FILTERS = {"actor", "action", "entity_type", "outcome", "date_from", "date_to", "q"}


def handle_get(handler: Any, state: Any, parsed: Any, _user: dict) -> bool:
    path = parsed.path
    if path == "/api/ferramentas-destacadas":
        if not handler.require_admin():
            return True
        handler.json_response({"items": state.negocial_tools.list_highlighted_tools()})
        return True
    if path == "/api/config/alpha/ho/imports":
        if not handler.require_admin():
            return True
        query = parse_qs(parsed.query)
        handler.json_response(state.alpha_ho.list_imports(handler._int_query(query, "limit", 50)))
        return True
    match = re.fullmatch(r"/api/config/alpha/ho/imports/(\d+)", path)
    if match:
        if not handler.require_admin():
            return True
        try:
            handler.json_response(state.alpha_ho.get_import(int(match.group(1))))
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/config/alpha/ho/goals":
        if not handler.require_admin():
            return True
        query = parse_qs(parsed.query)
        handler.json_response(state.alpha_ho.list_goals((query.get("competence") or [""])[0]))
        return True
    if path == "/api/config/alpha/ho/rules":
        if not handler.require_admin():
            return True
        handler.json_response(state.alpha_ho.list_rules())
        return True
    if path == "/api/config/alpha/ho/calculations":
        if not handler.require_admin():
            return True
        query = parse_qs(parsed.query)
        handler.json_response(
            state.alpha_ho.calculation_summary((query.get("competence") or [""])[0])
        )
        return True
    match = re.fullmatch(r"/api/config/carteiras/([^/]+)/ferramentas", path)
    if match:
        if not handler.require_admin():
            return True
        try:
            handler.json_response(state.negocial_tools.wallet_tool_settings(match.group(1)))
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/config/ferramentas-negociais":
        if not handler.require_admin():
            return True
        handler.json_response({"items": state.negocial_tools.list_tools()})
        return True
    match = re.fullmatch(r"/api/config/ferramentas-negociais/(\d+)/registros/(\d+)/anexos/(\d+)", path)
    if match:
        if not handler.require_admin():
            return True
        try:
            filename, content, content_type = state.negocial_tools.attachment_file(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            )
            handler.file_response(filename, content, content_type)
        except (OSError, TypeError, ValueError) as exc:
            handler.error_response(str(exc), 404)
        return True
    match = re.fullmatch(r"/api/config/ferramentas-negociais/(\d+)/registros(?:/(\d+))?", path)
    if match:
        if not handler.require_admin():
            return True
        try:
            tool_id = int(match.group(1))
            if match.group(2):
                handler.json_response(state.negocial_tools.get_record(tool_id, int(match.group(2))))
            else:
                query = parse_qs(parsed.query)
                handler.json_response(state.negocial_tools.list_records(
                    tool_id,
                    status=(query.get("status") or [""])[0],
                    carteira=(query.get("carteira") or [""])[0],
                    usuario=(query.get("usuario") or [""])[0],
                    query=(query.get("q") or [""])[0],
                    limit=handler._int_query(query, "limit", 1000),
                ))
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    match = re.fullmatch(r"/api/config/ferramentas-negociais/(\d+)/relatorio\.xlsx", path)
    if match:
        if not handler.require_admin():
            return True
        try:
            query = parse_qs(parsed.query)
            filename, content = state.negocial_tools.report_xlsx(
                int(match.group(1)),
                {key: (values or [""])[0] for key, values in query.items()},
            )
            handler.file_response(
                filename,
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path.startswith("/api/config/ferramentas-negociais/"):
        if not handler.require_admin():
            return True
        try:
            tool_id = int(path.rsplit("/", 1)[-1])
            query = parse_qs(parsed.query)
            version_id = int((query.get("version_id") or [0])[0] or 0) or None
            handler.json_response({"item": state.negocial_tools.get_tool(tool_id, version_id)})
        except (TypeError, ValueError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/auditoria/geral":
        if not handler.require_permission("view_audit"):
            return True
        query = parse_qs(parsed.query)
        filters = {key: values[0] for key, values in query.items() if key in AUDIT_FILTERS}
        limit = handler._int_query(query, "limit", 500)
        handler.json_response({"ok": True, "items": state.repo.list_general_audit(limit, filters)})
        return True
    if path in {"/api/auditoria/geral.csv", "/api/auditoria/geral.xlsx"}:
        if not handler.require_permission("view_audit"):
            return True
        query = parse_qs(parsed.query)
        filters = {key: values[0] for key, values in query.items() if key in AUDIT_FILTERS}
        items = state.repo.list_general_audit(handler._int_query(query, "limit", 2000), filters)
        if path.endswith(".csv"):
            handler.csv_response("auditoria_geral.csv", handler.audit_csv(items))
        else:
            try:
                handler.file_response(
                    "auditoria_geral.xlsx",
                    handler.audit_xlsx(items),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except RuntimeError as exc:
                handler.error_response(str(exc), 500)
        return True
    if path == "/api/config/users":
        if not handler.require_permission("manage_users"):
            return True
        handler.json_response({"gerencial": state.repo.list_users(), "negociadores": state.negocial.list_users()})
        return True
    match = re.fullmatch(r"/api/config/users/negociador/(\d+)/goals", path)
    if match:
        if not handler.require_permission("manage_users"):
            return True
        try:
            handler.json_response(state.negocial.list_user_monthly_goals(int(match.group(1))))
        except ValueError as exc:
            handler.error_response(str(exc), 404)
        return True
    if path == "/api/config/permissoes":
        if not handler.require_admin():
            return True
        handler.json_response(state.repo.list_role_permissions())
        return True
    if path == "/api/config/permissoes/usuarios":
        if not handler.require_admin():
            return True
        handler.json_response(state.repo.list_user_permission_overrides())
        return True
    if path == "/api/diagnostico":
        if not handler.require_admin():
            return True
        handler.json_response(handler.diagnostic_payload())
        return True
    if path == "/api/backups/retention":
        if not handler.require_permission("manage_backups"):
            return True
        handler.json_response({"policy": state.backups.policy(), "last_run": state.backup_retention_status})
        return True
    if path == "/api/backups/database":
        if not handler.require_permission("manage_backups"):
            return True
        try:
            handler.json_response(state.database_backups.list_backups())
        except RuntimeError as exc:
            handler.error_response(str(exc), 500)
        return True
    if path == "/api/database/inventory":
        if not handler.require_admin():
            return True
        try:
            handler.json_response(state.database_maintenance.inventory())
        except RuntimeError as exc:
            handler.error_response(str(exc), 500)
        return True
    if path == "/api/database/monitoring":
        if not handler.require_admin():
            return True
        try:
            handler.json_response(state.database_monitoring.latest())
        except RuntimeError as exc:
            handler.error_response(str(exc), 500)
        return True
    if path == "/api/database/monitoring/history":
        if not handler.require_admin():
            return True
        query = parse_qs(parsed.query)
        try:
            handler.json_response(state.database_monitoring.history(handler._int_query(query, "limit", 96)))
        except RuntimeError as exc:
            handler.error_response(str(exc), 500)
        return True
    if path == "/api/backups/storage":
        if not handler.require_admin():
            return True
        handler.json_response(state.database_backups.storage_config())
        return True
    if path == "/api/config/attachments/storage":
        if not handler.require_admin():
            return True
        handler.json_response(state.attachment_storage.storage_config())
        return True
    if path == "/api/config/defasagem/source":
        if not handler.require_admin():
            return True
        handler.json_response(state.defasagem.source_config())
        return True
    if path == "/api/database/monitoring/status":
        if not handler.require_admin():
            return True
        try:
            handler.json_response(state.database_monitoring.status())
        except RuntimeError as exc:
            handler.error_response(str(exc), 500)
        return True
    if path == "/api/database/performance":
        if not handler.require_admin():
            return True
        query = parse_qs(parsed.query)
        try:
            handler.json_response(state.database_monitoring.performance(handler._int_query(query, "limit", 20)))
        except RuntimeError as exc:
            handler.error_response(str(exc), 500)
        return True
    if path == "/api/database/alerts":
        if not handler.require_admin():
            return True
        query = parse_qs(parsed.query)
        try:
            status = (query.get("status") or ["active"])[0]
            handler.json_response(state.database_monitoring.list_alerts(status, handler._int_query(query, "limit", 100)))
        except RuntimeError as exc:
            handler.error_response(str(exc), 500)
        return True
    if path == "/api/database/maintenance/status":
        if not handler.require_admin():
            return True
        handler.json_response(state.database_maintenance_status)
        return True
    return False


def handle_post(handler: Any, state: Any, path: str, user: dict) -> bool:
    if path == "/api/config/defasagem/source":
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            payload = handler.read_json()
            result = state.defasagem.configure_source_directory(str(payload.get("path") or ""))
            handler.audit(
                "defasagem_source_update",
                "defasagem",
                "source_directory",
                str(result.get("source", {}).get("path") or ""),
                {"files": result.get("source", {}).get("files", {})},
                admin,
            )
            handler.json_response(result)
        except (OSError, RuntimeError, ValueError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/config/attachments/storage":
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            payload = handler.read_json()
            result = state.attachment_storage.configure_storage(
                str(payload.get("path") or ""),
                bool(payload.get("migrate_existing", True)),
            )
            handler.audit(
                "attachment_storage_update",
                "attachment_storage",
                "storage",
                str(result.get("storage", {}).get("path") or ""),
                {"moved_attachments": result.get("moved_attachments", 0)},
                admin,
            )
            handler.json_response(result)
        except (OSError, RuntimeError, ValueError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/config/alpha/ho/imports/preview":
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            payload = handler.read_json()
            result = state.alpha_ho.preview_pdf(
                str(payload.get("file_name") or "metas-alpha.pdf"),
                str(payload.get("content_base64") or ""),
                str(admin.get("username") or ""),
            )
            handler.json_response(result, 201)
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    match = re.fullmatch(r"/api/config/alpha/ho/imports/(\d+)/apply", path)
    if match:
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            handler.json_response(
                state.alpha_ho.apply_import(
                    int(match.group(1)),
                    str(admin.get("username") or ""),
                )
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/config/alpha/ho/rules":
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            handler.json_response(
                state.alpha_ho.save_rule(
                    handler.read_json(),
                    str(admin.get("username") or ""),
                ),
                201,
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/config/alpha/ho/recalculate":
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            payload = handler.read_json()
            competences = payload.get("competences") or None
            handler.json_response(state.alpha_ho.recalculate(competences))
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    match = re.fullmatch(r"/api/config/alpha/ho/goals/(\d+)/override", path)
    if match:
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            handler.json_response(
                state.alpha_ho.override_goal(
                    int(match.group(1)),
                    handler.read_json(),
                    str(admin.get("username") or ""),
                ),
                201,
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    match = re.fullmatch(r"/api/config/carteiras/([^/]+)/ferramentas", path)
    if match:
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            payload = handler.read_json()
            result = state.negocial_tools.set_wallet_tool(
                match.group(1),
                str(payload.get("tool_key") or ""),
                bool(payload.get("enabled")),
                admin,
            )
            handler.audit(
                "wallet_tool_toggle",
                "carteira",
                match.group(1),
                match.group(1),
                {"tool_key": payload.get("tool_key"), "enabled": bool(payload.get("enabled"))},
                admin,
            )
            handler.json_response(result)
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/config/ferramentas-negociais":
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            item = state.negocial_tools.save_draft(handler.read_json(), admin)
            handler.audit("dynamic_tool_draft_save", "ferramenta", str(item["id"]), item["nome"], {"versao": item["versao"]}, admin)
            handler.json_response({"item": item}, 201)
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        except Exception:
            handler.error_response("Nao foi possivel salvar a ferramenta.", 500)
        return True
    match = re.fullmatch(r"/api/config/ferramentas-negociais/(\d+)/(ativar|inativar|excluir|restaurar)", path)
    if match:
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            tool_id = int(match.group(1))
            operation = match.group(2)
            if operation == "excluir":
                item = state.negocial_tools.delete_tool(tool_id, admin)
                handler.audit(
                    "dynamic_tool_delete_scheduled",
                    "ferramenta",
                    str(tool_id),
                    item["nome"],
                    {"purge_after": item["purge_after"]},
                    admin,
                )
                handler.json_response({"ok": True, "item": item})
            elif operation == "restaurar":
                item = state.negocial_tools.restore_tool(tool_id)
                handler.audit(
                    "dynamic_tool_restore", "ferramenta", str(tool_id), item["nome"], {}, admin
                )
                handler.json_response({"ok": True, "item": item})
            else:
                active = operation == "ativar"
                item = state.negocial_tools.set_tool_active(tool_id, active)
                handler.audit(
                    f"dynamic_tool_{operation}", "ferramenta", str(tool_id), item["nome"], {}, admin
                )
                handler.json_response({"item": item})
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    match = re.fullmatch(r"/api/config/ferramentas-negociais/(\d+)/registros/(\d+)/campos", path)
    if match:
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            tool_id = int(match.group(1))
            record_id = int(match.group(2))
            payload = handler.read_json()
            result = state.negocial_tools.update_record_field(
                tool_id,
                record_id,
                str(payload.get("campo") or ""),
                payload.get("valor"),
                admin,
            )
            handler.audit(
                "dynamic_tool_record_field_update",
                "ferramenta_registro",
                str(record_id),
                result["item"]["titulo"],
                {"tool_id": tool_id, "campo": payload.get("campo")},
                admin,
            )
            handler.json_response(result)
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    match = re.fullmatch(r"/api/config/ferramentas-negociais/(\d+)/registros/(\d+)/(transicao|comentarios)", path)
    if match:
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            tool_id = int(match.group(1))
            record_id = int(match.group(2))
            payload = handler.read_json()
            if match.group(3) == "transicao":
                result = state.negocial_tools.transition_record(
                    tool_id,
                    record_id,
                    str(payload.get("status") or ""),
                    str(payload.get("justificativa") or ""),
                    admin,
                )
                action = "dynamic_tool_record_transition"
            else:
                result = state.negocial_tools.add_comment(
                    tool_id,
                    record_id,
                    str(payload.get("texto") or ""),
                    admin,
                )
                action = "dynamic_tool_record_comment"
            handler.audit(action, "ferramenta_registro", str(record_id), result["item"]["titulo"], {"tool_id": tool_id}, admin)
            handler.json_response(result)
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    match = re.fullmatch(r"/api/config/ferramentas-negociais/(\d+)/(publicar|nova-versao)", path)
    if match:
        admin = handler.require_admin()
        if not admin:
            return True
        try:
            tool_id = int(match.group(1))
            if match.group(2) == "publicar":
                item = state.negocial_tools.publish(tool_id, admin)
                action = "dynamic_tool_publish"
            else:
                item = state.negocial_tools.create_next_version(tool_id, admin)
                action = "dynamic_tool_new_version"
            handler.audit(action, "ferramenta", str(tool_id), item["nome"], {"versao": item["versao"]}, admin)
            handler.json_response({"item": item}, 201)
        except (TypeError, ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    return False
