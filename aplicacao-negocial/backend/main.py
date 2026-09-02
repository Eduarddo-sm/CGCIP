import asyncio
import logging
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.config import settings
from backend.database import SessionLocal, engine
from backend.models import User
from backend.observability import configure_logging, request_id, request_id_context
from backend.routes.admin import router as admin_router
from backend.routes.auth import router as auth_router
from backend.routes.correcoes import router as correcoes_router
from backend.routes.ferramentas import router as ferramentas_router
from backend.routes.pareceres import router as pareceres_router
from backend.routes.producao import router as producao_router
from backend.services.bootstrap_service import create_database, seed_admin_user
from backend.services.producao_service import auto_break_previous_month_items
from backend.services.schema_migration_service import run_schema_migrations

configure_logging(settings.log_level)
logger = logging.getLogger("negocial.http")
app = FastAPI(title="Negocial Web")
rollover_task = None

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"


@app.middleware("http")
async def prevent_stale_frontend_assets(request, call_next):
    started = time.perf_counter()
    current_request_id = request_id(request.headers.get("X-Request-ID"))
    token = request_id_context.set(current_request_id)
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        logger.exception(
            "request_failed",
            extra={"method": request.method, "path": request.url.path, "status": status_code},
        )
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "duration_ms": duration_ms,
                "client": request.client.host if request.client else "",
            },
        )
        request_id_context.reset(token)
    response.headers["X-Request-ID"] = current_request_id
    path = request.url.path
    if path in {"/", "/login"} or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(producao_router, prefix="/api")
app.include_router(pareceres_router, prefix="/api")
app.include_router(correcoes_router, prefix="/api")
app.include_router(ferramentas_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.on_event("startup")
def startup():
    run_schema_migrations(settings.database_url, BASE_DIR)
    create_database()
    db = SessionLocal()
    try:
        seed_admin_user(db)
    finally:
        db.close()


def _run_rollover_maintenance() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.active.is_(True), User.role != "ADMIN").all()
        for user in users:
            auto_break_previous_month_items(db, user)
    except Exception:
        db.rollback()
        logger.exception("monthly_rollover_maintenance_failed")
    finally:
        db.close()


async def _rollover_worker() -> None:
    while True:
        await asyncio.to_thread(_run_rollover_maintenance)
        await asyncio.sleep(900)


@app.on_event("startup")
async def start_rollover_worker():
    global rollover_task
    rollover_task = asyncio.create_task(_rollover_worker())


@app.on_event("shutdown")
async def stop_rollover_worker():
    global rollover_task
    if rollover_task:
        rollover_task.cancel()
        try:
            await rollover_task
        except asyncio.CancelledError:
            pass


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "negocial-web", "checks": {"process": "ok"}}


@app.get("/api/health/live")
def liveness_check():
    return {"status": "ok", "app": "negocial-web"}


@app.get("/api/health/ready")
def readiness_check():
    started = time.perf_counter()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "app": "negocial-web",
            "checks": {"database": "ok"},
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:
        logger.exception("readiness_failed")
        return JSONResponse(status_code=503, content={
            "status": "not_ready",
            "app": "negocial-web",
            "checks": {"database": "error"},
            "detail": type(exc).__name__,
        })


@app.get("/login")
def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/")
def index_page():
    return FileResponse(FRONTEND_DIR / "index.html")
