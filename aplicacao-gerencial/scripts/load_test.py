from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
NEGOCIAL_ROOT = ROOT.parent / "aplicacao-negocial"


@dataclass(frozen=True)
class RequestMetric:
    service: str
    path: str
    elapsed_ms: float
    ok: bool
    status: int
    error: str = ""


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def request_json(opener, service: str, base_url: str, path: str, method: str = "GET", payload=None) -> tuple[RequestMetric, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", "Connection": "close"},
    )
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=30) as response:
            content = response.read()
            result = json.loads(content.decode("utf-8")) if content else {}
            metric = RequestMetric(service, path, (time.perf_counter() - started) * 1000, True, response.status)
            return metric, result
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return RequestMetric(service, path, (time.perf_counter() - started) * 1000, False, exc.code, detail[:300]), {}
    except (URLError, TimeoutError, OSError) as exc:
        return RequestMetric(service, path, (time.perf_counter() - started) * 1000, False, 0, str(exc)), {}


def virtual_user(
    barrier: threading.Barrier,
    gerencial_url: str,
    gerencial_username: str,
    gerencial_password: str,
    negocial_url: str,
    negocial_username: str,
    negocial_password: str,
) -> list[RequestMetric]:
    metrics: list[RequestMetric] = []
    barrier.wait(timeout=30)
    for service, base_url, username, password, paths in (
        ("gerencial", gerencial_url, gerencial_username, gerencial_password, ["/api/me", "/api/carteiras", "/api/negociadores"]),
        ("negocial", negocial_url, negocial_username, negocial_password, ["/api/me", "/api/producao/schema", "/api/producao"]),
    ):
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        login_metric, _ = request_json(opener, service, base_url, "/api/login", "POST", {"username": username, "password": password})
        metrics.append(login_metric)
        if not login_metric.ok:
            continue
        for path in paths:
            metric, _ = request_json(opener, service, base_url, path)
            metrics.append(metric)
        logout_metric, _ = request_json(opener, service, base_url, "/api/logout", "POST", {})
        if not logout_metric.ok and logout_metric.status == 0:
            # The Windows HTTP stack may abort the client socket after the
            # server has already completed a concurrent logout. Confirm the
            # endpoint once on a fresh connection before counting a failure.
            retry_opener = build_opener(HTTPCookieProcessor(CookieJar()))
            logout_metric, _ = request_json(retry_opener, service, base_url, "/api/logout", "POST", {})
        metrics.append(logout_metric)
    return metrics


def manage_negocial_user(action: str, username: str, password: str = "") -> None:
    python = NEGOCIAL_ROOT / ".venv" / "Scripts" / "python.exe"
    helper = NEGOCIAL_ROOT / "tests" / "e2e_user.py"
    command = [str(python), str(helper), action, username]
    if password:
        command.append(password)
    subprocess.run(command, cwd=NEGOCIAL_ROOT, check=True, timeout=60)


def summarize(
    metrics: list[RequestMetric],
    elapsed: float,
    users: int,
    max_p95_ms: float,
    max_auth_p95_ms: float,
    max_error_percent: float,
    min_throughput: float,
) -> dict:
    durations = [item.elapsed_ms for item in metrics]
    failed = [item for item in metrics if not item.ok]
    by_service = {}
    for service in {item.service for item in metrics}:
        selected = [item for item in metrics if item.service == service]
        service_times = [item.elapsed_ms for item in selected]
        by_service[service] = {
            "requests": len(selected),
            "errors": sum(not item.ok for item in selected),
            "p50_ms": round(statistics.median(service_times), 2),
            "p95_ms": round(percentile(service_times, 0.95), 2),
            "max_ms": round(max(service_times), 2),
        }
    by_path = {}
    for key in sorted({f"{item.service}:{item.path}" for item in metrics}):
        service, path = key.split(":", 1)
        selected = [item for item in metrics if item.service == service and item.path == path]
        path_times = [item.elapsed_ms for item in selected]
        by_path[key] = {
            "requests": len(selected),
            "errors": sum(not item.ok for item in selected),
            "p50_ms": round(statistics.median(path_times), 2),
            "p95_ms": round(percentile(path_times, 0.95), 2),
            "max_ms": round(max(path_times), 2),
        }
    error_rate = round((len(failed) / max(1, len(metrics))) * 100, 2)
    p95_ms = round(percentile(durations, 0.95), 2)
    business_durations = [item.elapsed_ms for item in metrics if item.path not in {"/api/login", "/api/logout"}]
    auth_durations = [item.elapsed_ms for item in metrics if item.path in {"/api/login", "/api/logout"}]
    business_p95_ms = round(percentile(business_durations, 0.95), 2)
    auth_p95_ms = round(percentile(auth_durations, 0.95), 2)
    throughput = round(len(metrics) / max(elapsed, 0.001), 2)
    slo = {
        "max_p95_ms": max_p95_ms,
        "max_auth_p95_ms": max_auth_p95_ms,
        "max_error_percent": max_error_percent,
        "min_throughput_requests_second": min_throughput,
        "business_p95_ok": business_p95_ms <= max_p95_ms,
        "auth_p95_ok": auth_p95_ms <= max_auth_p95_ms,
        "error_rate_ok": error_rate <= max_error_percent,
        "throughput_ok": throughput >= min_throughput,
    }
    return {
        "ok": all((slo["business_p95_ok"], slo["auth_p95_ok"], slo["error_rate_ok"], slo["throughput_ok"])),
        "requests_ok": not failed,
        "virtual_users": users,
        "requests": len(metrics),
        "errors": len(failed),
        "error_rate_percent": error_rate,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_requests_second": throughput,
        "p50_ms": round(statistics.median(durations), 2),
        "p95_ms": p95_ms,
        "business_p95_ms": business_p95_ms,
        "auth_p95_ms": auth_p95_ms,
        "max_ms": round(max(durations), 2),
        "slo": slo,
        "services": by_service,
        "paths": by_path,
        "failures": [item.__dict__ for item in failed[:10]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste autenticado de carga dos sistemas Gerencial e Negocial.")
    parser.add_argument("--users", type=int, default=25)
    parser.add_argument("--gerencial-url", default=os.getenv("GERENCIAL_LOAD_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--negocial-url", default=os.getenv("NEGOCIAL_LOAD_URL", "http://127.0.0.1:8890"))
    parser.add_argument("--max-p95-ms", type=float, default=float(os.getenv("LOAD_MAX_P95_MS", "500")))
    parser.add_argument("--max-auth-p95-ms", type=float, default=float(os.getenv("LOAD_MAX_AUTH_P95_MS", "1500")))
    parser.add_argument("--max-error-percent", type=float, default=float(os.getenv("LOAD_MAX_ERROR_PERCENT", "1")))
    parser.add_argument("--min-throughput", type=float, default=float(os.getenv("LOAD_MIN_THROUGHPUT", "5")))
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    if not 1 <= args.users <= 100:
        raise SystemExit("O numero de usuarios deve estar entre 1 e 100.")
    gerencial_username = os.getenv("GERENCIAL_LOAD_USERNAME", "")
    gerencial_password = os.getenv("GERENCIAL_LOAD_PASSWORD", "")
    if not gerencial_username or not gerencial_password:
        raise SystemExit("Defina GERENCIAL_LOAD_USERNAME e GERENCIAL_LOAD_PASSWORD.")

    negocial_username = f"__e2e_negocial_load_{uuid.uuid4().hex[:10]}"
    negocial_password = f"Load-{uuid.uuid4()}"
    manage_negocial_user("create", negocial_username, negocial_password)
    try:
        barrier = threading.Barrier(args.users)
        started = time.perf_counter()
        all_metrics: list[RequestMetric] = []
        with ThreadPoolExecutor(max_workers=args.users) as pool:
            futures = [
                pool.submit(
                    virtual_user,
                    barrier,
                    args.gerencial_url,
                    gerencial_username,
                    gerencial_password,
                    args.negocial_url,
                    negocial_username,
                    negocial_password,
                )
                for _ in range(args.users)
            ]
            for future in as_completed(futures):
                all_metrics.extend(future.result())
        result = summarize(
            all_metrics,
            time.perf_counter() - started,
            args.users,
            args.max_p95_ms,
            args.max_auth_p95_ms,
            args.max_error_percent,
            args.min_throughput,
        )
        result["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report = Path(args.report) if args.report else ROOT / "data" / "reports" / "load" / f"load_test_{time.strftime('%Y%m%d_%H%M%S')}.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["report"] = str(report.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    finally:
        manage_negocial_user("delete", negocial_username)


if __name__ == "__main__":
    raise SystemExit(main())
