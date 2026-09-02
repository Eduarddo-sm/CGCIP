from __future__ import annotations

import json
import csv
import io
import logging
import mimetypes
import os
import shutil
import socket
import zipfile
from xml.sax.saxutils import escape as xml_escape
import ssl
import subprocess
import sys
import threading
import time
from email.utils import formatdate
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from backend.config import ROOT, settings
from backend.app_state import AppState
from backend.routes import dispatch_get, dispatch_post, dispatch_put
from services.excel_reader import ExcelReadError
from services.colchao_service import ColchaoError
from services.login_rate_limit import login_rate_limiter
from services.observability import configure_logging, new_request_id
from services.parecer_service import ParecerError
from services.protocolo_service import ProtocoloError


ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
UI_DIR = settings.ui_dir
DATA_DIR = settings.data_dir
DATABASE_URL = settings.database_url
configure_logging(os.environ.get("NEGOCIADORES_LOG_LEVEL", "INFO"))
http_logger = logging.getLogger("gerencial.http")


state = AppState(ROOT, DATA_DIR, DATABASE_URL)


class ThreadingHTTPSServer(ThreadingHTTPServer):
    def __init__(self, server_address, request_handler_class, ssl_context: ssl.SSLContext):
        super().__init__(server_address, request_handler_class)
        self.ssl_context = ssl_context

    def get_request(self):
        request, address = self.socket.accept()
        request.settimeout(15)
        return request, address

    def process_request(self, request, client_address) -> None:
        # TLS handshakes must not run in the accept loop. A stale browser socket
        # would otherwise delay every other user until its timeout expires.
        worker = threading.Thread(
            target=self._process_tls_request,
            args=(request, client_address),
            daemon=True,
            name=f"https-{client_address[0]}:{client_address[1]}",
        )
        worker.start()

    def _process_tls_request(self, request, client_address) -> None:
        try:
            first_byte = request.recv(1, socket.MSG_PEEK)
        except (TimeoutError, OSError):
            request.close()
            return
        if first_byte and first_byte != b"\x16":
            self._redirect_plain_http(request)
            return
        try:
            wrapped = self.ssl_context.wrap_socket(request, server_side=True)
        except (ssl.SSLError, TimeoutError, OSError):
            request.close()
            return
        # The short timeout above protects only the TLS handshake. Report
        # generation and file downloads may legitimately take longer.
        wrapped.settimeout(300)
        try:
            self.finish_request(wrapped, client_address)
        except Exception:
            self.handle_error(wrapped, client_address)
        finally:
            self.shutdown_request(wrapped)

    def _redirect_plain_http(self, request) -> None:
        try:
            payload = request.recv(8192).decode("iso-8859-1", errors="ignore")
            lines = payload.split("\r\n")
            request_parts = lines[0].split(" ") if lines else []
            path = request_parts[1] if len(request_parts) >= 2 and request_parts[1].startswith("/") else "/"
            host = next((line[5:].strip() for line in lines[1:] if line.lower().startswith("host:")), "")
            if not host or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:[]" for char in host):
                host = f"{self.server_name}:{self.server_port}"
            location = f"https://{host}{path}"
            body = b"Redirecionando para conexao segura."
            response = (
                "HTTP/1.1 308 Permanent Redirect\r\n"
                f"Location: {location}\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + body
            request.sendall(response)
        except (TimeoutError, OSError):
            pass
        finally:
            request.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "NegociadoresHTTP/2.0-auth"

    def log_message(self, format: str, *args) -> None:
        return

    def handle_one_request(self) -> None:
        self._request_started = time.perf_counter()
        self._response_status = 500
        self._request_id = ""
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self._response_status = 499
            http_logger.info(
                "client_disconnected",
                extra=self._request_log_fields(499),
            )
        except Exception:
            http_logger.exception(
                "request_failed",
                extra=self._request_log_fields(500),
            )
            raise
        finally:
            if getattr(self, "requestline", ""):
                http_logger.info(
                    "request_completed",
                    extra=self._request_log_fields(getattr(self, "_response_status", 500)),
                )

    def _request_log_fields(self, status: int) -> dict:
        started = getattr(self, "_request_started", time.perf_counter())
        return {
            "request_id": getattr(self, "_request_id", "") or "-",
            "method": getattr(self, "command", ""),
            "path": urlparse(getattr(self, "path", "")).path,
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "client": self.client_address[0] if getattr(self, "client_address", None) else "",
        }

    def send_response(self, code: int, message: str | None = None) -> None:
        self._response_status = code
        super().send_response(code, message)

    def end_headers(self) -> None:
        if not getattr(self, "_request_id", ""):
            headers = getattr(self, "headers", None)
            self._request_id = new_request_id(headers.get("X-Request-ID") if headers else None)
        self.send_header("X-Request-ID", self._request_id)
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/api/health", "/api/health/live"}:
            self.json_response({"ok": True, "status": "ok", "app": "gerencial", "time": time.time()})
            return
        if parsed.path == "/api/health/ready":
            self._readiness_response()
            return
        if self._is_public_static(parsed.path):
            self.serve_static(parsed.path)
            return
        if parsed.path == "/api/me":
            user = self.require_user()
            if user:
                self.json_response({"user": self.user_payload(user)})
            return
        user = self.require_user(redirect=True)
        if not user:
            return
        if parsed.path == "/api/negociadores":
            if not self.require_permission("monitoramento_read"):
                return
            self.json_response(state.service.list_negociadores())
            return
        if parsed.path == "/api/carteiras":
            query = parse_qs(parsed.query)
            include_inactive = query.get("include_inactive", ["0"])[0] in {"1", "true", "yes"}
            negocial_by_slug = {}
            try:
                for item in state.negocial.list_carteiras():
                    negocial_by_slug[str(item.get("slug") or item.get("nome") or "").upper()] = item
            except Exception:
                negocial_by_slug = {}
            items = []
            for item in state.repo.list_carteiras(include_inactive=include_inactive):
                clone = dict(item)
                key = str(clone.get("nome") or "").upper().replace(" ", "_")
                clone["negocial"] = negocial_by_slug.get(key)
                items.append(clone)
            self.json_response({"items": items, "negocial": list(negocial_by_slug.values())})
            return
        if parsed.path == "/api/carteiras/schema/versions":
            user = self.require_permission("view_schema_versions")
            if not user:
                return
            query = parse_qs(parsed.query)
            try:
                self.json_response(state.negocial.carteira_schema_versions(query.get("carteira", [""])[0]))
            except (ValueError, RuntimeError) as exc:
                self.error_response(str(exc), 400)
            return
        if parsed.path == "/api/overview":
            query = parse_qs(parsed.query)
            filters = {key: values[0] for key, values in query.items() if key in {"usuario", "data", "tipo", "prioridade"}}
            status = query.get("status", ["unread"])[0]
            overview = state.overview.list_items(user["username"], filters, status)
            client_version = query.get("version", [""])[0]
            if client_version:
                self.json_response(state.overview.payload(overview, client_version))
            else:
                self.json_response(overview)
            return
        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["1500"])[0] or "1500")
            self.json_response(state.service.get_all_events(limit=max(100, min(limit, 5000))))
            return
        if dispatch_get(self, state, parsed, user):
            return
        if parsed.path == "/api/notificacoes":
            query = parse_qs(parsed.query)
            client_version = query.get("version", [""])[0]
            self.handle_notifications(lambda: self._notifications_payload(user["username"], client_version))
            return
        if parsed.path == "/api/background/status":
            self.json_response({"optimizer": state.optimizer.status(), "maintenance": state.maintenance_scheduler.status()})
            return
        if parsed.path == "/api/notes":
            query = parse_qs(parsed.query)
            target_type = query.get("target_type", [""])[0]
            target_id = query.get("target_id", [""])[0]
            self.json_response(state.repo.list_notes(target_type, target_id))
            return
        if parsed.path.startswith("/api/negociadores/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 3:
                try:
                    negociador_id = int(parts[2])
                except ValueError:
                    self.error_response("Negociador invalido", 400)
                    return
                if len(parts) == 4 and parts[3] == "data":
                    self.json_response(state.service.get_table_data(negociador_id))
                    return
                if len(parts) == 4 and parts[3] == "snapshot":
                    query = parse_qs(parsed.query)
                    self.json_response(state.service.get_month_snapshot(negociador_id, query.get("month", [""])[0]))
                    return
                if len(parts) == 4 and parts[3] == "events":
                    self.json_response(state.service.get_events(negociador_id))
                    return
                if len(parts) == 4 and parts[3] == "timeline":
                    self.json_response(state.service.get_timeline(negociador_id))
                    return
                if len(parts) == 4 and parts[3] == "corrections":
                    query = parse_qs(parsed.query)
                    limit = int(query.get("limit", ["200"])[0] or "200")
                    self.json_response(state.service.get_corrections(negociador_id, limit))
                    return
                if len(parts) == 5 and parts[3] == "events":
                    self.json_response(state.service.get_event(int(parts[4])))
                    return
                if len(parts) == 4 and parts[3] == "refresh":
                    try:
                        self.json_response(state.service.refresh_negociador(negociador_id, force=True))
                    except (ValueError, ExcelReadError) as exc:
                        self.error_response(str(exc), 400)
                    return
        self.serve_static(parsed.path)

    def _is_public_static(self, path: str) -> bool:
        if path in ("/login.html", "/styles.css", "/app.js"):
            return True
        if path.startswith(("/assets/", "/core/", "/features/", "/layout/", "/templates/")):
            return True
        return Path(path).suffix.lower() in {".js", ".css", ".map", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".woff", ".woff2"}

    def do_POST(self) -> None:
        if self.path == "/api/login":
            payload = self.read_json()
            username = str(payload.get("username", "")).strip()
            client = self.client_address[0] if self.client_address else "unknown"
            rate_key = f"{client}:{username.lower()}"
            retry_after = login_rate_limiter.retry_after(rate_key)
            if retry_after:
                self.audit("login_blocked", "auth", username, username, {"retry_after": retry_after}, None, outcome="failed")
                self.json_response({"error": f"Muitas tentativas. Tente novamente em {retry_after} segundos."}, 429, headers=[("Retry-After", str(retry_after))])
                return
            user = state.repo.authenticate_user(username, str(payload.get("password", "")))
            if not user:
                login_rate_limiter.failure(rate_key)
                self.audit("login_failed", "auth", username, username, {"reason": "invalid_credentials"}, None, outcome="failed")
                self.error_response("Usuario ou senha invalidos", 401)
                return
            login_rate_limiter.success(rate_key)
            token = state.repo.create_session(user["username"])
            self.audit("login_success", "auth", str(user["id"]), user["username"], {}, user)
            self.json_response({"ok": True, "user": self.user_payload(user)}, headers=[self.session_cookie(token)])
            return
        if self.path == "/api/logout":
            user = state.repo.get_user_by_session(self.session_token())
            state.repo.delete_session(self.session_token())
            self.audit("logout", "auth", str(user.get("id", "")) if user else "", user.get("username", "") if user else "", {}, user)
            self.json_response({"ok": True}, headers=[self.expired_session_cookie()])
            return
        user = self.require_user()
        if not user:
            return
        if self.path == "/api/sheets":
            if not self.require_permission("monitoramento_write"):
                return
            payload = self.read_json()
            try:
                self.json_response({
                    "sheets": state.reader.list_sheets(
                        str(payload.get("path") or ""),
                        str(payload.get("password") or "") or None,
                    )
                })
            except ExcelReadError as exc:
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/negociadores":
            if not self.require_permission("monitoramento_write"):
                return
            payload = self.read_json()
            try:
                result = state.service.create_negociador(payload)
                self.json_response(result, 201)
            except (ValueError, ExcelReadError) as exc:
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/carteiras":
            admin = self.require_permission("edit_schema")
            if not admin:
                return
            payload = self.read_json()
            try:
                carteira = state.repo.create_carteira(
                    str(payload.get("nome", "")),
                    str(payload.get("descricao", "")),
                )
                negocial = None
                if payload.get("sync_negocial"):
                    negocial = state.negocial.upsert_carteira(
                        str(payload.get("nome", "")),
                        str(payload.get("descricao", "")),
                        list(payload.get("colunas") or []),
                        dict(payload.get("regras_ho") or {}),
                    )
                    if str(payload.get("nome") or "").strip().upper() == "ALPHA":
                        state.alpha_ho.recalculate_active()
                self.audit("carteira_create", "carteira", str(carteira.get("id") or ""), str(carteira.get("nome") or payload.get("nome") or ""), {"sync_negocial": bool(payload.get("sync_negocial"))}, admin)
                self.json_response({"ok": True, "carteira": carteira, "negocial": negocial}, 201)
            except ValueError as exc:
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/overview/read":
            payload = self.read_json()
            try:
                self.json_response(state.overview.mark_read(payload.get("id", ""), user["username"]))
            except ValueError as exc:
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/overview/read-all":
            payload = self.read_json()
            filters = {key: payload.get(key, "") for key in ("usuario", "data", "tipo", "prioridade")}
            self.json_response(state.overview.mark_all_read(user["username"], filters))
            return
        if self.path == "/api/background/refresh":
            self.json_response(state.optimizer.refresh_all())
            return
        if self.path == "/api/database/maintenance":
            admin = self.require_admin()
            if not admin:
                return
            payload = self.read_json()
            try:
                self.json_response(state.database_maintenance.cleanup(payload))
            except RuntimeError as exc:
                self.error_response(str(exc), 500)
            return
        if self.path == "/api/database/monitoring/collect":
            admin = self.require_admin()
            if not admin:
                return
            try:
                result = state.database_monitoring.collect()
                self.audit("database_monitoring_collect", "database", str(result.get("snapshot_id", "")), "PostgreSQL", {"alerts": len(result.get("alerts", []))}, admin)
                self.json_response(result, 201)
            except RuntimeError as exc:
                self.error_response(str(exc), 500)
            return
        if self.path == "/api/database/alerts/acknowledge":
            admin = self.require_admin()
            if not admin:
                return
            payload = self.read_json()
            try:
                result = state.database_monitoring.acknowledge_alert(int(payload.get("id", 0)), admin["username"])
                self.audit("database_alert_acknowledge", "database_alert", str(payload.get("id", "")), "PostgreSQL", {}, admin)
                self.json_response(result)
            except (TypeError, ValueError) as exc:
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/database/alerts/test":
            admin = self.require_admin()
            if not admin:
                return
            result = state.database_monitoring.create_test_alert(admin["username"])
            self.audit("database_alert_test", "database_alert", str(result.get("alert", {}).get("id", "")), "PostgreSQL", {}, admin)
            self.json_response(result, 201)
            return
        if self.path == "/api/backups/storage":
            admin = self.require_admin()
            if not admin:
                return
            payload = self.read_json()
            try:
                result = state.database_backups.configure_storage(
                    str(payload.get("path") or ""),
                    bool(payload.get("migrate_existing")),
                )
                self.audit(
                    "backup_storage_update",
                    "database_backup",
                    "storage",
                    str(result.get("storage", {}).get("path") or ""),
                    {"moved_backups": result.get("moved_backups", 0)},
                    admin,
                )
                self.json_response(result)
            except RuntimeError as exc:
                self.audit("backup_storage_update", "database_backup", "storage", "", {"error": str(exc)}, admin, outcome="failed")
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/backups/database":
            admin = self.require_permission("manage_backups")
            if not admin:
                return
            try:
                result = state.database_backups.create_backup()
                self.audit("backup_create", "database_backup", result.get("backup", {}).get("name", ""), result.get("backup", {}).get("name", ""), {"size_bytes": result.get("backup", {}).get("size_bytes")}, admin)
                self.json_response(result, 201)
            except RuntimeError as exc:
                self.audit("backup_create", "database_backup", "", "", {"error": str(exc)}, admin, outcome="failed")
                self.error_response(str(exc), 500)
            return
        if self.path == "/api/backups/database/restore":
            admin = self.require_permission("restore_backup")
            if not admin:
                return
            payload = self.read_json()
            if not self.require_critical_confirmation(payload):
                return
            try:
                result = state.database_backups.restore_backup(str(payload.get("name", "")))
                self.audit("backup_restore", "database_backup", str(payload.get("name", "")), str(payload.get("name", "")), {"pre_restore_backup": result.get("pre_restore_backup"), "motivo": payload.get("motivo")}, admin)
                self.json_response(result)
            except RuntimeError as exc:
                self.audit("backup_restore", "database_backup", str(payload.get("name", "")), str(payload.get("name", "")), {"error": str(exc)}, admin, outcome="failed")
                self.error_response(str(exc), 400)
            return
        post_path = self.path.split("?", 1)[0].rstrip("/")
        if post_path == "/api/monitoramento/planilha/celula":
            if not self.require_permission("monitoramento_write"):
                return
            payload = self.read_json()
            try:
                result, baseline = state.service.execute_gerencial_change(
                    lambda: state.negocial.update_gerencial_cell(
                        int(payload.get("id") or payload.get("row_id") or 0),
                        str(payload.get("header", "")),
                        payload.get("value", ""),
                        user["username"],
                        str(payload.get("motivo", "")),
                    )
                )
                result["monitoring_suppressed"] = bool(baseline.get("ok"))
                self.audit(
                    "production_cell_update",
                    "producao",
                    str(result.get("id") or ""),
                    str(result.get("owner_username") or ""),
                    {
                        "campo": result.get("header"),
                        "antes": result.get("previous_value"),
                        "depois": result.get("value"),
                        "motivo": payload.get("motivo", ""),
                        "origem": "gerencial",
                        "monitoramento_omitido": bool(baseline.get("ok")),
                    },
                    user,
                )
                self.json_response(result)
            except (ValueError, RuntimeError) as exc:
                self.error_response(str(exc), 400)
            return
        if post_path == "/api/monitoramento/planilha/cliente":
            if not self.require_permission("monitoramento_write"):
                return
            payload = self.read_json()
            try:
                self.json_response(state.negocial.create_gerencial_client(payload, user["username"]), 201)
            except (ValueError, RuntimeError) as exc:
                self.error_response(str(exc), 400)
            return
        if post_path == "/api/monitoramento/planilha/deletar":
            allowed = self.require_permission("delete_agreements")
            if not allowed:
                return
            payload = self.read_json()
            if not self.require_critical_confirmation(payload):
                return
            try:
                self.json_response(state.negocial.delete_producao(
                    int(payload.get("id") or payload.get("row_id") or 0),
                    user["username"],
                ))
            except (ValueError, RuntimeError) as exc:
                self.error_response(str(exc), 400)
            return
        if post_path == "/api/monitoramento/fechamento":
            admin = self.require_admin()
            if not admin:
                return
            payload = self.read_json()
            try:
                result = state.negocial.close_month(
                    str(payload.get("carteira", "")),
                    int(payload.get("mes") or 0),
                    int(payload.get("ano") or 0),
                    user["username"],
                )
                self.audit(
                    "monthly_close",
                    "monitoramento",
                    f"{payload.get('carteira')}-{payload.get('ano')}-{payload.get('mes')}",
                    "Fechamento mensal",
                    result,
                    user,
                )
                self.json_response(result)
            except (ValueError, RuntimeError) as exc:
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/notificacoes/read":
            payload = self.read_json()
            self.handle_notifications(lambda: state.notifications.dismiss(str(payload.get("id", "")), user["username"]))
            return
        if self.path == "/api/config/users":
            admin = self.require_permission("manage_users")
            if not admin:
                return
            payload = self.read_json()
            try:
                user_type = str(payload.get("type") or payload.get("source") or "gerencial").strip().lower()
                if user_type == "negociador":
                    username = str(payload.get("username", "")).strip()
                    carteira = str(payload.get("carteira", "")).strip()
                    meta_pagamento = payload.get("meta_pagamento") or 70000
                    user_record = state.negocial.upsert_user(
                        username,
                        str(payload.get("password", "")),
                        carteira,
                        meta_pagamento,
                        payload.get("enabled_tools"),
                    )
                    negociador_id = state.repo.upsert_system_negociador_login({
                        "nome": username,
                        "carteira": carteira,
                        "arquivo_path": f"negocial://{username}",
                        "sheet": NegocialService.PRODUCAO_SHEET,
                        "negocial_user_id": user_record["id"],
                        "negocial_username": username,
                        "meta_pagamento": user_record.get("meta_pagamento") or meta_pagamento,
                    })
                    self.audit("user_create", "negociador", str(user_record.get("id") or ""), username, {"carteira": carteira, "enabled_tools": payload.get("enabled_tools")}, admin)
                    self.json_response({"ok": True, "negocial_user": user_record, "negociador_id": negociador_id}, 201)
                    return
                requested_role = str(payload.get("role", "user")).strip().lower()
                if requested_role == "superadmin" and str(admin.get("role") or "").lower() != "superadmin":
                    self.error_response("Somente um superadministrador pode criar outro superadministrador.", 403)
                    return
                created = state.repo.create_user(
                    str(payload.get("username", "")).strip(),
                    str(payload.get("password", "")),
                    requested_role,
                )
                self.audit("user_create", "gerencial", str(created.get("id") or ""), str(created.get("username") or ""), {"role": created.get("role")}, admin)
                self.json_response(created, 201)
            except ValueError as exc:
                self.error_response(str(exc), 400)
            except Exception:
                http_logger.exception(
                    "user_create_failed",
                    extra={
                        **self._request_log_fields(500),
                        "user_type": str(payload.get("type") or payload.get("source") or "gerencial"),
                        "target_username": str(payload.get("username") or "").strip(),
                    },
                )
                self.error_response("Nao foi possivel cadastrar o usuario.", 500)
            return
        if self.path == "/api/config/permissoes":
            admin = self.require_admin()
            if not admin:
                return
            payload = self.read_json()
            result = state.repo.save_role_permissions(payload)
            self.audit("permissions_update", "role_permissions", "", "Permissões por perfil", payload, admin)
            self.json_response(result)
            return
        if self.path == "/api/config/permissoes/usuarios":
            admin = self.require_admin()
            if not admin:
                return
            payload = self.read_json()
            try:
                result = state.repo.save_user_permission_overrides(int(payload.get("user_id") or 0), dict(payload.get("overrides") or {}))
                self.audit("user_permissions_update", "user_permissions", str(payload.get("user_id") or ""), result.get("user", {}).get("username", ""), {"overrides": payload.get("overrides")}, admin)
                self.json_response(result)
            except ValueError as exc:
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/notes":
            payload = self.read_json()
            target_type = str(payload.get("target_type", "")).strip()
            target_id = str(payload.get("target_id", "")).strip()
            text = str(payload.get("text", "")).strip()
            if not target_type or not target_id or not text:
                self.error_response("Observacao invalida", 400)
                return
            self.json_response(state.repo.create_note(target_type, target_id, text, user["username"]), 201)
            return
        if dispatch_post(self, state, self.path.split("?", 1)[0].rstrip("/"), user):
            return
        parts = self.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "negociadores"] and parts[3] == "abrir-planilha":
            try:
                negociador = state.repo.get_negociador(int(parts[2]))
                if not negociador or not negociador.get("active"):
                    self.error_response("Negociador nao encontrado", 404)
                    return
                if negociador.get("source_type") == "sistema":
                    self.error_response("Este negociador usa o sistema negocial e nao possui planilha para abrir.", 400)
                    return
                self.json_response(self.open_local_file(Path(str(negociador["arquivo_path"]))))
            except OSError as exc:
                self.error_response(str(exc), 400)
            return
        self.error_response("Rota nao encontrada", 404)

    def do_PUT(self) -> None:
        current_user = self.require_user()
        if not current_user:
            return
        if dispatch_put(self, state, self.path.split("?", 1)[0].rstrip("/"), current_user):
            return
        parts = self.path.strip("/").split("/")
        if len(parts) == 6 and parts[:3] == ["api", "config", "users"] and parts[3] == "gerencial" and parts[5] == "settings":
            superadmin = self.require_roles("superadmin", message="Somente um superadministrador pode editar usuarios gerenciais.")
            if not superadmin:
                return
            target_id = int(parts[4])
            payload = self.read_json()
            target = state.repo.get_user(target_id)
            if not target:
                self.error_response("Usuario nao encontrado.", 404)
                return
            requested_role = str(payload.get("role") or target.get("role") or "user").lower()
            if target.get("role") == "superadmin" and requested_role != "superadmin" and state.repo.active_superadmin_count() <= 1:
                self.error_response("O ultimo superadministrador ativo nao pode ser rebaixado.", 400)
                return
            try:
                result = state.repo.update_user(
                    target_id,
                    str(payload.get("username") or target.get("username") or ""),
                    requested_role,
                    str(payload.get("password") or ""),
                )
                self.audit("user_update", "gerencial", str(target_id), str(result.get("username") or ""), {
                    "previous_role": target.get("role"),
                    "role": result.get("role"),
                    "password_changed": bool(payload.get("password")),
                }, superadmin)
                self.json_response(result)
            except ValueError as exc:
                self.error_response(str(exc), 400)
            return
        if self.path == "/api/backups/database/verify":
            admin = self.require_permission("manage_backups")
            if not admin:
                return
            payload = self.read_json()
            try:
                result = state.database_backups.verify_backup(str(payload.get("name", "")))
                self.audit("backup_verify", "database_backup", str(payload.get("name", "")), str(payload.get("name", "")), {"sha256": result.get("sha256")}, admin)
                self.json_response(result)
            except RuntimeError as exc:
                self.audit("backup_verify", "database_backup", str(payload.get("name", "")), str(payload.get("name", "")), {"error": str(exc)}, admin, outcome="failed")
                self.error_response(str(exc), 400)
            return
        if len(parts) == 6 and parts[:3] == ["api", "config", "users"] and parts[3] == "negociador" and parts[5] == "settings":
            admin = self.require_permission("manage_users")
            if not admin:
                return
            target_id = int(parts[4])
            payload = self.read_json()
            try:
                user_record = state.negocial.update_user_settings(target_id, payload, updated_by=admin.get("username"))
                state.repo.upsert_system_negociador_login({
                    "nome": user_record["username"],
                    "carteira": user_record.get("carteira") or "",
                    "arquivo_path": f"negocial://{user_record['username']}",
                    "sheet": NegocialService.PRODUCAO_SHEET,
                    "negocial_user_id": user_record["id"],
                    "negocial_username": user_record["username"],
                    "meta_pagamento": user_record.get("meta_pagamento") or payload.get("meta_pagamento") or 70000,
                })
                self.audit("user_update", "negociador", str(user_record.get("id") or target_id), str(user_record.get("username") or ""), {
                    "carteira": user_record.get("carteira"),
                    "meta_pagamento": user_record.get("meta_pagamento"),
                    "meta_competencia": payload.get("meta_competencia"),
                    "enabled_tools": user_record.get("enabled_tools"),
                    "password_changed": bool(payload.get("password")),
                }, admin)
                self.json_response({"ok": True, "negocial_user": user_record})
            except ValueError as exc:
                self.error_response(str(exc), 400)
            return
        if (len(parts) == 4 and parts[:3] == ["api", "config", "users"] and parts[3].isdigit()) or (len(parts) == 5 and parts[:3] == ["api", "config", "users"] and parts[4].isdigit()):
            admin = self.require_permission("manage_users")
            if not admin:
                return
            source = parts[3] if len(parts) == 5 else "gerencial"
            target_id = int(parts[4] if len(parts) == 5 else parts[3])
            payload = self.read_json()
            is_settings_update = source == "negociador" and any(
                key in payload for key in ("password", "carteira", "meta_pagamento", "meta_competencia", "enabled_tools")
            )
            if is_settings_update:
                try:
                    user_record = state.negocial.update_user_settings(target_id, payload, updated_by=admin.get("username"))
                    state.repo.upsert_system_negociador_login({
                        "nome": user_record["username"],
                        "carteira": user_record.get("carteira") or "",
                        "arquivo_path": f"negocial://{user_record['username']}",
                        "sheet": NegocialService.PRODUCAO_SHEET,
                        "negocial_user_id": user_record["id"],
                        "negocial_username": user_record["username"],
                        "meta_pagamento": user_record.get("meta_pagamento") or payload.get("meta_pagamento") or 70000,
                    })
                    self.audit("user_update", "negociador", str(user_record.get("id") or target_id), str(user_record.get("username") or ""), {
                        "carteira": user_record.get("carteira"),
                        "meta_pagamento": user_record.get("meta_pagamento"),
                        "meta_competencia": payload.get("meta_competencia"),
                        "enabled_tools": user_record.get("enabled_tools"),
                        "password_changed": bool(payload.get("password")),
                    }, admin)
                    self.json_response({"ok": True, "negocial_user": user_record})
                except ValueError as exc:
                    self.error_response(str(exc), 400)
                return
            active = bool(payload.get("active"))
            if source == "gerencial" and target_id == int(admin["id"]) and not active:
                self.error_response("Voce nao pode desativar o usuario logado.", 400)
                return
            target = state.repo.get_user(target_id) if source == "gerencial" else None
            if target and str(target.get("role") or "").lower() in {"admin", "superadmin"} and str(admin.get("role") or "").lower() != "superadmin":
                self.error_response("Somente um superadministrador pode alterar o acesso de administradores.", 403)
                return
            if target and target.get("role") == "superadmin" and not active and state.repo.active_superadmin_count() <= 1:
                self.error_response("O ultimo superadministrador ativo nao pode ser desativado.", 400)
                return
            try:
                if source == "negociador":
                    result = state.negocial.set_user_active(target_id, active)
                else:
                    result = state.repo.set_user_active(target_id, active)
                self.audit("user_activate" if active else "user_deactivate", source, str(target_id), str(result.get("username") or ""), {"active": active}, admin)
                self.json_response(result)
            except ValueError as exc:
                self.error_response(str(exc), 404)
            return
        if len(parts) == 3 and parts[:2] == ["api", "negociadores"]:
            if not self.require_permission("monitoramento_write"):
                return
            payload = self.read_json()
            try:
                self.json_response(state.service.update_negociador(int(parts[2]), payload))
            except (ValueError, ExcelReadError) as exc:
                self.error_response(str(exc), 400)
            return
        parts = self.path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "notes"]:
            payload = self.read_json()
            text = str(payload.get("text", "")).strip()
            if not text:
                self.error_response("Observacao invalida", 400)
                return
            try:
                self.json_response(state.repo.update_note(int(parts[2]), text, self.require_user()["username"]))
            except ValueError as exc:
                self.error_response(str(exc), 404)
            return
        self.error_response("Rota nao encontrada", 404)

    def do_DELETE(self) -> None:
        current_user = self.require_user()
        if not current_user:
            return
        parts = self.path.strip("/").split("/")
        if (len(parts) == 4 and parts[:3] == ["api", "config", "users"] and parts[3].isdigit()) or (len(parts) == 5 and parts[:3] == ["api", "config", "users"] and parts[4].isdigit()):
            admin = self.require_permission("manage_users")
            if not admin:
                return
            source = parts[3] if len(parts) == 5 else "gerencial"
            target_id = int(parts[4] if len(parts) == 5 else parts[3])
            if source == "gerencial" and target_id == int(admin["id"]):
                self.error_response("Voce nao pode excluir o usuario logado.", 400)
                return
            target = state.repo.get_user(target_id) if source == "gerencial" else None
            if target and str(target.get("role") or "").lower() in {"admin", "superadmin"} and str(admin.get("role") or "").lower() != "superadmin":
                self.error_response("Somente um superadministrador pode excluir administradores.", 403)
                return
            if target and target.get("role") == "superadmin" and state.repo.active_superadmin_count() <= 1:
                self.error_response("O ultimo superadministrador ativo nao pode ser excluido.", 400)
                return
            try:
                if source == "negociador":
                    state.negocial.delete_user_login(target_id)
                else:
                    state.repo.delete_user_login(target_id)
                self.audit("user_delete_login", source, str(target_id), "", {}, admin)
                self.json_response({"ok": True})
            except ValueError as exc:
                self.error_response(str(exc), 404)
            return
        if len(parts) == 3 and parts[:2] == ["api", "carteiras"]:
            admin = self.require_permission("edit_schema")
            if not admin:
                return
            payload = self.read_json()
            if not self.require_critical_confirmation(payload):
                return
            nome = unquote(parts[2])
            try:
                result = state.repo.deactivate_carteira(nome)
                try:
                    state.negocial.deactivate_carteira(nome)
                except ValueError:
                    pass
                self.audit("carteira_deactivate", "carteira", nome, nome, {}, admin)
                self.json_response(result)
            except ValueError as exc:
                self.error_response(str(exc), 400)
            return
        if len(parts) == 3 and parts[:2] == ["api", "negociadores"]:
            if not self.require_permission("monitoramento_write"):
                return
            state.service.delete_negociador(int(parts[2]))
            self.json_response({"ok": True})
            return
        self.error_response("Rota nao encontrada", 404)

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        target = (UI_DIR / path.lstrip("/")).resolve()
        if not str(target).startswith(str(UI_DIR.resolve())) or not target.exists() or target.is_dir():
            self.error_response("Arquivo nao encontrado", 404)
            return
        stat = target.stat()
        etag = f'W/"{stat.st_size}-{stat.st_mtime_ns}"'
        cache_control = self._static_cache_control(target)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control)
            self.end_headers()
            return
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static_cache_control(self, target: Path) -> str:
        ui_root = UI_DIR.resolve()
        if target in (ui_root / "index.html", ui_root / "login.html"):
            return "no-cache"
        if target.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".woff", ".woff2"}:
            return "public, max-age=86400, must-revalidate"
        return "public, max-age=0, must-revalidate"

    def require_user(self, redirect: bool = False) -> dict | None:
        user = state.repo.get_user_by_session(self.session_token())
        if user:
            return user
        if redirect and not self.path.startswith("/api/"):
            self.send_response(302)
            self.send_header("Location", "/login.html")
            self.end_headers()
            return None
        else:
            self.error_response("Login necessario", 401)
        return None

    def require_admin(self) -> dict | None:
        return self.require_roles("admin", "superadmin", message="Permissao de administrador necessaria.")

    def require_roles(self, *roles: str, message: str | None = None) -> dict | None:
        user = self.require_user()
        if not user:
            return None
        allowed = {str(role).lower() for role in roles}
        if str(user.get("role", "")).lower() not in allowed:
            self.error_response(message or "Permissao insuficiente.", 403)
            return None
        return user

    def require_permission(self, permission: str) -> dict | None:
        user = self.require_user()
        if not user:
            return None
        if not state.repo.has_permission(str(user.get("role", "")), permission, int(user.get("id") or 0)):
            self.error_response("Permissao insuficiente.", 403)
            return None
        return user

    def user_payload(self, user: dict) -> dict:
        payload = dict(user)
        payload["permissions"] = state.repo.permissions_for_role(str(user.get("role", "")), int(user.get("id") or 0))
        return payload

    def audit(
        self,
        action: str,
        entity_type: str,
        entity_id: str = "",
        entity_label: str = "",
        details: dict | None = None,
        actor: dict | None = None,
        outcome: str = "success",
    ) -> None:
        try:
            actor = actor or state.repo.get_user_by_session(self.session_token()) or {}
            state.repo.create_general_audit({
                "actor": actor.get("username") or "",
                "actor_role": actor.get("role") or "",
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_label": entity_label,
                "outcome": outcome,
                "details": details or {},
                "ip_address": self.client_address[0] if self.client_address else "",
            })
        except Exception:
            return

    def session_token(self) -> str | None:
        cookie_header = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get("negociadores_session")
        return morsel.value if morsel else None

    def session_cookie(self, token: str) -> tuple[str, str]:
        secure = "; Secure" if settings.secure_cookies else ""
        return ("Set-Cookie", f"negociadores_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000{secure}")

    def expired_session_cookie(self) -> tuple[str, str]:
        secure = "; Secure" if settings.secure_cookies else ""
        return ("Set-Cookie", f"negociadores_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure}")

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _int_query(self, query: dict, name: str, fallback: int) -> int:
        try:
            return int(query.get(name, [fallback])[0] or fallback)
        except (TypeError, ValueError):
            return fallback

    def require_critical_confirmation(self, payload: dict) -> bool:
        if str(payload.get("confirmacao") or "").strip().upper() != "CONFIRMAR":
            self.error_response("Digite CONFIRMAR para executar esta ação crítica.", 400)
            return False
        if not str(payload.get("motivo") or "").strip():
            self.error_response("Informe o motivo da ação crítica.", 400)
            return False
        return True

    def audit_rows(self, items: list[dict]) -> list[list[str]]:
        rows = [["Data/Hora", "Usuario", "Perfil", "Acao", "Entidade", "ID", "Rotulo", "Resultado", "IP", "Detalhes"]]
        for item in items:
            rows.append([
                str(item.get("created_at") or ""),
                str(item.get("actor") or ""),
                str(item.get("actor_role") or ""),
                str(item.get("action") or ""),
                str(item.get("entity_type") or ""),
                str(item.get("entity_id") or ""),
                str(item.get("entity_label") or ""),
                str(item.get("outcome") or ""),
                str(item.get("ip_address") or ""),
                json.dumps(item.get("details") or {}, ensure_ascii=False, default=str),
            ])
        return rows

    def audit_csv(self, items: list[dict]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerows(self.audit_rows(items))
        return ("\ufeff" + buffer.getvalue()).encode("utf-8")

    def audit_xlsx(self, items: list[dict]) -> bytes:
        output = io.BytesIO()
        rows_xml = []
        for row_index, row in enumerate(self.audit_rows(items), start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                ref = f"{self.excel_column(col_index)}{row_index}"
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(str(value or ""))}</t></is></c>')
            rows_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        sheet_xml = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(rows_xml)}</sheetData></worksheet>'
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
            zf.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            zf.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Auditoria" sheetId="1" r:id="rId1"/></sheets></workbook>')
            zf.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        return output.getvalue()

    def excel_column(self, index: int) -> str:
        result = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def diagnostic_payload(self) -> dict:
        def port_state(port: int) -> str:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return "online"
            except OSError:
                return "offline"
        return {
            "ok": True,
            "time": time.time(),
            "host": socket.gethostname(),
            "frontend_version": "20260713-role-permissions-1",
            "database": {
                "backend": state.repo.backend,
                "maintenance": state.database_maintenance_status,
                "monitoring": state.database_monitoring.latest(),
                "pool": state.repo.pool_stats(),
            },
            "services": {
                "gerencial": {"port": int(os.environ.get("NEGOCIADORES_PORT", "8765")), "status": "online"},
                "negocial": {"port": 8890, "status": port_state(8890)},
            },
            "backups": {
                "retention": state.backup_retention_status,
                "database_count": len(state.database_backups.list_backups().get("items", [])),
                "scheduler": state.maintenance_scheduler.status(),
            },
        }

    def json_response(self, payload, status: int = 200, headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for key, value in headers or []:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def error_response(self, message: str, status: int = 500) -> None:
        self.json_response({"error": message}, status)

    def _readiness_response(self) -> None:
        started = time.perf_counter()
        try:
            with state.repo.connect() as connection:
                connection.execute("SELECT 1")
            self.json_response({
                "ok": True,
                "status": "ready",
                "app": "gerencial",
                "checks": {"database": "ok", "monitor": "ok" if state.monitor else "error"},
                "database_pool": state.repo.pool_stats(),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            })
        except Exception as exc:
            http_logger.exception("readiness_failed")
            self.json_response({
                "ok": False,
                "status": "not_ready",
                "app": "gerencial",
                "checks": {"database": "error"},
                "detail": type(exc).__name__,
            }, 503)

    def csv_response(self, filename: str, content: bytes) -> None:
        self.file_response(filename, content, "text/csv; charset=utf-8")

    def file_response(self, filename: str, content: bytes, content_type: str) -> None:
        clean_filename = Path(filename).name.replace("\r", "").replace("\n", "")
        fallback_filename = clean_filename.encode("ascii", "ignore").decode().replace('"', "_") or "download"
        safe_filename = quote(clean_filename)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{fallback_filename}\"; filename*=UTF-8''{safe_filename}",
        )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def open_local_file(self, file_path: Path) -> dict:
        target = Path(file_path).expanduser()
        if not target.exists():
            raise OSError(f"Arquivo nao encontrado: {target}")
        resolved = target.resolve()
        excel_path = self._excel_executable() if resolved.suffix.lower() in {".xlsx", ".xlsm", ".xls"} else None
        if excel_path:
            subprocess.Popen([str(excel_path), str(resolved)], close_fds=True)
            return {"ok": True, "path": str(resolved), "opener": "excel"}
        os.startfile(str(resolved))
        return {"ok": True, "path": str(resolved), "opener": "default"}

    def _excel_executable(self) -> Path | None:
        candidates = [
            os.environ.get("EXCEL_EXE", ""),
            r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
            r"C:\Program Files (x86)\Microsoft Office\Root\Office16\EXCEL.EXE",
            r"C:\Program Files\Microsoft Office\Office16\EXCEL.EXE",
            r"C:\Program Files (x86)\Microsoft Office\Office16\EXCEL.EXE",
            shutil.which("EXCEL.EXE") or "",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                return path
        return None

    def handle_parecer(self, action) -> None:
        try:
            self.json_response(action())
        except (ParecerError, OSError) as exc:
            self.error_response(str(exc), 400)

    def handle_notifications(self, action) -> None:
        try:
            self.json_response(action())
        except (ValueError, ParecerError) as exc:
            self.error_response(str(exc), 400)

    def _notifications_payload(self, username: str, client_version: str = "") -> dict:
        payload = state.notifications.list_notifications(username)
        if client_version and payload.get("version") == client_version:
            return {
                "changed": False,
                "version": payload.get("version", ""),
                "count": payload.get("count", 0),
                "overview": payload.get("overview", 0),
                "pareceres": payload.get("pareceres", 0),
                "protocolos": payload.get("protocolos", 0),
                "ferramentas": payload.get("ferramentas", 0),
            }
        return {"changed": True, **payload}

    def handle_protocolo(self, action) -> None:
        try:
            self.json_response(action())
        except ProtocoloError as exc:
            self.error_response(str(exc), 400)

    def handle_colchao(self, action) -> None:
        try:
            self.json_response(action())
        except (ColchaoError, OSError) as exc:
            self.error_response(str(exc), 400)

    def _mark_parecer_and_notification(self, pk: str, username: str) -> dict:
        result = state.parecer.marcar_solicitado(pk, username)
        state.notifications.dismiss_parecer(pk, username)
        state.optimizer.refresh_parecer()
        return result

    def _mark_pareceres_and_notifications(self, pks: list[str], username: str) -> dict:
        result = state.parecer.marcar_varios(pks, username)
        state.notifications.dismiss_pareceres([str(pk) for pk in pks], username)
        state.optimizer.refresh_parecer()
        return result

    def _approve_parecer(self, pk: str, reason: str, descricao: str, username: str) -> dict:
        result = state.parecer.aprovar_negocial(pk, reason, descricao, username)
        state.optimizer.refresh_parecer()
        return result

    def _reject_parecer(self, pk: str, reason: str, descricao: str, username: str) -> dict:
        result = state.parecer.reprovar_negocial(pk, reason, descricao, username)
        state.notifications.dismiss_parecer(pk, username)
        state.optimizer.refresh_parecer()
        return result

    def _refresh_parecer_powerquery(self, username: str) -> dict:
        result = state.parecer.refresh_powerquery(username)
        state.optimizer.refresh_parecer()
        return result

    def _update_colchao_status(self, payload: dict, username: str) -> dict:
        profile = str(payload.get("profile", "alpha"))
        result = state.colchao.update_status(
            int(payload.get("row", 0)),
            str(payload.get("status", "")),
            str(payload.get("observacao", "")),
            username,
            profile,
            str(payload.get("sheet", "")),
        )
        state.optimizer.refresh_colchao(profile)
        return result

    def _update_colchao_status_batch(self, payload: dict, username: str) -> dict:
        profile = str(payload.get("profile", "alpha"))
        result = state.colchao.update_status_batch(
            list(payload.get("changes") or []),
            username,
            profile,
            str(payload.get("sheet", "")),
        )
        state.optimizer.refresh_colchao(profile)
        return result

    def _create_colchao_agreement(self, payload: dict, username: str) -> dict:
        profile = str(payload.get("profile", "alpha"))
        result = state.colchao.create_agreement(payload, username)
        state.optimizer.refresh_colchao(profile)
        return result

    def _sync_colchao(self, profile: str) -> dict:
        result = state.colchao.sync_from_excel(profile)
        state.optimizer.refresh_colchao(profile)
        return result


def main() -> None:
    host = os.environ.get("NEGOCIADORES_HOST", "0.0.0.0")
    port = int(os.environ.get("NEGOCIADORES_PORT", "8765"))
    protocol = "http"
    default_cert = DATA_DIR / "certs" / "negociadores-local.crt"
    default_key = DATA_DIR / "certs" / "negociadores-local.key"
    cert_file = Path(os.environ.get("NEGOCIADORES_SSL_CERT", "").strip() or default_cert)
    key_file = Path(os.environ.get("NEGOCIADORES_SSL_KEY", "").strip() or default_key)
    if cert_file.is_file() and key_file.is_file():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
        server = ThreadingHTTPSServer((host, port), Handler, context)
        protocol = "https"
    else:
        server = ThreadingHTTPServer((host, port), Handler)
    display_host = "SEU-IP" if host == "0.0.0.0" else host
    try:
        print(f"Monitor de Negociadores rodando em {protocol}://{display_host}:{port}")
    except OSError:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.monitor.stop()
        state._database_maintenance_stop.set()
        state.maintenance_scheduler.stop()
        state.repo.close()
        server.server_close()
