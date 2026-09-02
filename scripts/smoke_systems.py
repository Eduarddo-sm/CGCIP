from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener


def request_json(opener, base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "X-Request-ID": f"smoke-{int(time.time())}"},
    )
    started = time.perf_counter()
    with opener.open(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
        elapsed = int((time.perf_counter() - started) * 1000)
        print(f"OK {method:4} {path:28} {response.status} {elapsed:4} ms")
        return data


def check_app(name: str, base_url: str, username: str, password: str, core_paths: list[str]) -> list[str]:
    print(f"\n{name}: {base_url}")
    errors: list[str] = []
    tls_context = ssl.create_default_context()
    if os.environ.get("PROJETO_NEGOCIAL_VERIFY_TLS", "").strip().lower() not in {"1", "true", "sim"}:
        tls_context.check_hostname = False
        tls_context.verify_mode = ssl.CERT_NONE
    opener = build_opener(HTTPCookieProcessor(CookieJar()), HTTPSHandler(context=tls_context))
    try:
        ready = request_json(opener, base_url, "/api/health/ready")
        if ready.get("status") != "ready":
            errors.append(f"{name}: servidor nao esta pronto")
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        return [f"{name}: health check falhou: {exc}"]
    if not username or not password:
        print("SKIP login: defina usuario e senha nas variaveis de ambiente")
        return errors
    try:
        request_json(opener, base_url, "/api/login", "POST", {"username": username, "password": password})
        request_json(opener, base_url, "/api/me")
        for path in core_paths:
            request_json(opener, base_url, path)
        request_json(opener, base_url, "/api/logout", "POST", {})
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        errors.append(f"{name}: fluxo autenticado falhou: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste de fumaca dos sistemas Gerencial e Negocial.")
    parser.add_argument("--host", default=os.environ.get("PROJETO_NEGOCIAL_HOST", "127.0.0.1"))
    parser.add_argument("--gerencial-url", default=os.environ.get("GERENCIAL_BASE_URL", ""))
    parser.add_argument("--negocial-url", default=os.environ.get("NEGOCIAL_BASE_URL", ""))
    args = parser.parse_args()
    errors = []
    errors.extend(check_app(
        "Gerencial",
        args.gerencial_url or f"https://{args.host}:8765",
        os.environ.get("GERENCIAL_SMOKE_USERNAME", ""),
        os.environ.get("GERENCIAL_SMOKE_PASSWORD", ""),
        ["/api/carteiras", "/api/negociadores"],
    ))
    errors.extend(check_app(
        "Negocial",
        args.negocial_url or f"http://{args.host}:8890",
        os.environ.get("NEGOCIAL_SMOKE_USERNAME", ""),
        os.environ.get("NEGOCIAL_SMOKE_PASSWORD", ""),
        ["/api/producao/schema", "/api/producao"],
    ))
    if errors:
        print("\nFALHAS:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("\nTodos os checks executados passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
