import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select, func
from api.auth.router import router as auth_router
from api.conversations.router import router as conversations_router
from api.memories.router import router as memories_router
from api.chat.router import router as chat_router
from api.database import close_pool, database_session
from api.models import User
from config import settings
from observability import configure_logging


@asynccontextmanager
async def lifespan(app):
    if len(settings.auth.secret_key.get_secret_value().encode()) < 32:
        raise RuntimeError("JWT_SECRET_KEY debe tener al menos 32 bytes")
    if not settings.openrouter.api_key.get_secret_value():
        raise RuntimeError("OPENROUTER_API_KEY debe estar configurada en la API")
    configure_logging()
    yield
    close_pool()


app = FastAPI(title="Nexo API", version="2.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(memories_router)
app.include_router(chat_router)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.monotonic()
    request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logging.getLogger(__name__).info("http_request", extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status_code": response.status_code, "duration_ms": int((time.monotonic() - started) * 1000)})
    return response


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
def readiness():
    try:
        with database_session() as db:
            db.scalar(select(func.count()).select_from(User))
    except Exception as error:
        logging.getLogger(__name__).warning("database_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(503, "Database unavailable") from error
    return {"status": "ready"}
