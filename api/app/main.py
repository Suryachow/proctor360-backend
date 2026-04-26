import logging
import asyncio
import uuid
from datetime import datetime
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
import httpx

from app.api.deps import decode_access_token
from app.core.config import settings
from app.api.v1 import admin, auth, compliance, enterprise, exam, innovations, phase1, support
from app.db.session import Base, SessionLocal, engine
from app.models import entities  # Import all entities to ensure they are registered with Base
from app.models.entities import AuditLog, Tenant, Student
from app.core.security import hash_password
from app.observability import (
    IDEMPOTENCY_CLEANUP_DELETED_TOTAL,
    IDEMPOTENCY_CLEANUP_RUNS_TOTAL,
    RATE_LIMIT_BLOCKS_TOTAL,
    metrics_asgi_app,
    observe_http_request,
    set_rate_limiter_state,
    set_readiness_degraded,
    setup_logging,
)
from app.services.idempotency import delete_expired_idempotency_records
from app.services.idempotency_cleanup import run_idempotency_cleanup_loop
from app.services.rate_limiter import HybridRateLimiter
from app.services.ws_manager import ws_manager


setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Proctor360 AI API", version="2.0.0")

rate_limiter = HybridRateLimiter()

_cleanup_stop_event = asyncio.Event()
_cleanup_task: asyncio.Task | None = None


def _request_actor_identifier(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
            subject = str(payload.get("sub") or "").strip().lower()
            if subject:
                return f"user:{subject}"
        except Exception:
            pass

    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


def _path_rate_limit(path: str) -> int:
    if path.startswith("/api/v1/auth"):
        return max(1, settings.rate_limit_auth_per_minute)
    if path.startswith("/api/v1/exam/frame") or path.startswith("/api/v1/exam/event"):
        return max(1, settings.rate_limit_proctor_per_minute)
    return max(1, settings.rate_limit_general_per_minute)


app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list or ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Ensure CORS headers are present even on unhandled 500 errors
@app.exception_handler(Exception)
async def global_cors_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in [
        "http://localhost:5173", "http://localhost:5174",
        "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:5174",
        "http://localhost:5173", "http://localhost:5174",
    ]:
        headers["access-control-allow-origin"] = origin
        headers["access-control-allow-credentials"] = "true"
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers=headers,
    )

app.include_router(auth.router, prefix="/api/v1")
app.include_router(exam.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(compliance.router, prefix="/api/v1")
app.include_router(enterprise.router, prefix="/api/v1")
app.include_router(support.router, prefix="/api/v1")
app.include_router(phase1.router, prefix="/api/v1")
app.include_router(innovations.router, prefix="/api/v1")

if settings.observability_enable_metrics:
    app.mount("/api/v1/metrics", metrics_asgi_app())

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "timestamp": str(datetime.now())}


@app.get("/api/v1/ready")
async def readiness_check():
    db_ok = False
    ai_ok = False
    limiter_redis_healthy = rate_limiter.redis_healthy()
    limiter_degraded = rate_limiter.is_degraded

    set_rate_limiter_state(rate_limiter.mode, limiter_redis_healthy)
    set_readiness_degraded("rate_limiter_fallback_local", limiter_degraded)

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(f"{settings.ai_engine_url}/health")
            ai_ok = response.status_code == 200
    except Exception:
        ai_ok = False

    ready = db_ok and ai_ok and (not limiter_degraded)
    status_code = 200 if ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "ready": ready,
            "db": db_ok,
            "ai_engine": ai_ok,
            "rate_limiter_mode": rate_limiter.mode,
            "rate_limiter_redis_healthy": limiter_redis_healthy,
            "degraded_reasons": ["rate_limiter_fallback_local"] if limiter_degraded else [],
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

@app.on_event("startup")
def ensure_enterprise_schema():
    try:
        if settings.jwt_secret == "replace_me" or len(settings.jwt_secret) < 24:
            logger.warning("JWT_SECRET is weak or default; set a long random secret before production deployment.")

        Base.metadata.create_all(bind=engine)
        
        # Helper for SQLite-compatible ALTER TABLE
        def safe_add_column(table: str, col: str, col_type: str):
            try:
                with engine.begin() as conn:
                    # SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we just try and catch
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                    logger.info(f"Added column {col} to {table}")
            except Exception as e:
                # If column exists, SQLite will throw an error
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    pass
                else:
                    logger.debug(f"Note: Could not add column {col} to {table} (might already exist): {e}")

        safe_add_column("exams", "otp_plain", "VARCHAR(20)")
        safe_add_column("students", "registered_face_image", "TEXT")
        safe_add_column("questions", "sub_topic", "VARCHAR(120)")
        safe_add_column("exam_sessions", "device_fingerprint", "VARCHAR(255)")
        safe_add_column("exam_sessions", "registered_face_image", "TEXT")
        safe_add_column("exam_sessions", "registered_id_image", "TEXT")
        safe_add_column("exam_sessions", "report_data", "JSON")
        safe_add_column("exam_sessions", "device_integrity_score", "DOUBLE PRECISION DEFAULT 100.0")
        safe_add_column("exam_sessions", "attention_score", "DOUBLE PRECISION DEFAULT 100.0")
        safe_add_column("exam_sessions", "behavioral_consistency_score", "DOUBLE PRECISION DEFAULT 100.0")
        safe_add_column("exam_sessions", "multi_camera_enabled", "BOOLEAN DEFAULT FALSE")
        safe_add_column("exam_sessions", "audio_enabled", "BOOLEAN DEFAULT FALSE")
        safe_add_column("exam_sessions", "eye_tracking_enabled", "BOOLEAN DEFAULT FALSE")
        safe_add_column("exam_answers", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        safe_add_column("violations", "ai_confidence", "DOUBLE PRECISION")
        safe_add_column("violations", "policy_category", "VARCHAR(20)")
        safe_add_column("violations", "policy_action", "VARCHAR(30)")
        safe_add_column("violations", "human_review_required", "BOOLEAN DEFAULT FALSE")
        safe_add_column("violations", "explainability", "TEXT")
        
        db = SessionLocal()
        try:
            if not db.query(Tenant).filter(Tenant.slug == "default").first():
                db.add(Tenant(slug="default", name="Proctor Enterprise Default", is_active=True))
                db.commit()
            
            email = "student@test.com"
            if not db.query(Student).filter(Student.email == email).first():
                db.add(Student(
                    email=email,
                    password_hash=hash_password("Student123!"),
                    device_hash="PROCTOR_ENTERPRISE_DEMO",
                    registered_face_image="placeholder"
                ))
                db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Database synchronization failure: %s", exc)


@app.on_event("startup")
async def start_background_workers():
    global _cleanup_task
    _cleanup_stop_event.clear()

    # Run one cleanup pass at startup to avoid stale row accumulation.
    db = SessionLocal()
    try:
        deleted = delete_expired_idempotency_records(db)
        db.commit()
        IDEMPOTENCY_CLEANUP_RUNS_TOTAL.inc()
        if deleted > 0:
            IDEMPOTENCY_CLEANUP_DELETED_TOTAL.inc(deleted)
            logger.info("startup_idempotency_cleanup", extra={"deleted": deleted})
    except Exception:
        db.rollback()
        logger.exception("startup_idempotency_cleanup_failed")
    finally:
        db.close()

    _cleanup_task = asyncio.create_task(run_idempotency_cleanup_loop(_cleanup_stop_event))



@app.on_event("shutdown")
async def stop_background_workers():
    global _cleanup_task
    _cleanup_stop_event.set()
    if _cleanup_task is not None:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        _cleanup_task = None

@app.websocket("/ws/admin")
async def websocket_admin_endpoint(websocket: WebSocket, token: str = Query(None)):
    """Distributed proctoring telemetry bridge."""
    if not token:
        await websocket.close(code=1008)
        return
    
    try:
        # Minimal verification for demo infrastructure
        payload = decode_access_token(token)
        if not payload or payload.get("role") != "admin":
            await websocket.close(code=1008)
            return
            
        await ws_manager.connect("admin", websocket)
        try:
            while True:
                # Keep session alive and await signals
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect("admin", websocket)
    except Exception:
        await websocket.close(code=1011)

@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start_time = datetime.now()

    actor_key = _request_actor_identifier(request)
    set_rate_limiter_state(rate_limiter.mode, rate_limiter.redis_healthy())
    limit = _path_rate_limit(request.url.path)
    decision = rate_limiter.allow(f"{actor_key}:{request.url.path}", limit=limit, window_seconds=60)
    if not decision.allowed:
        RATE_LIMIT_BLOCKS_TOTAL.labels(path=request.url.path).inc()
        duration = (datetime.now() - start_time).total_seconds()
        observe_http_request(request.method, request.url.path, 429, duration)
        logger.warning(
            "rate_limit_blocked",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 429,
                "duration_ms": int(duration * 1000),
                "actor": actor_key,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded",
                "request_id": request_id,
            },
            headers={"Retry-After": str(decision.retry_after_seconds), "x-request-id": request_id},
        )

    if request.method == "OPTIONS":
        response = await call_next(request)
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["x-request-id"] = request_id
        duration = (datetime.now() - start_time).total_seconds()
        observe_http_request(request.method, request.url.path, response.status_code, duration)
        return response

    response = await call_next(request)
    duration = (datetime.now() - start_time).total_seconds()
    observe_http_request(request.method, request.url.path, response.status_code, duration)

    logger.info(
        "http_request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": int(duration * 1000),
            "actor": actor_key,
            "client_ip": request.client.host if request.client else "unknown",
        },
    )

    response.headers["x-request-id"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    if settings.enforce_https_headers:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Audit logging for state-changing or proctoring routes
    if request.method in ["POST", "PUT", "DELETE"] or "/api/v1/exam" in request.url.path:
        db = SessionLocal()
        try:
            token = request.headers.get("Authorization")
            actor_email = "anonymous"
            actor_role = "public"
            if token and token.startswith("Bearer "):
                try:
                    payload = decode_access_token(token[7:])
                    actor_email = payload.get("sub", "unknown")
                    # Heuristic for role in demo
                    actor_role = "student" if "student" in actor_email else "admin"
                except: pass

            log_entry = AuditLog(
                actor_email=actor_email,
                actor_role=actor_role,
                action=f"{request.method} {request.url.path} [{request_id}] ({duration:.3f}s)",
                resource="API_GATEWAY",
                status_code=response.status_code,
                ip_address=request.client.host if request.client else "unknown",
                user_agent=request.headers.get("User-Agent", "unknown")
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            logger.error(f"Audit log failure: {e}")
        finally:
            db.close()
            
    return response

@app.get("/")
def read_root(): return {"message": "Proctor360 Enterprise AI is online."}
