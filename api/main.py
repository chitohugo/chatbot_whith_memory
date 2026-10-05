from fastapi import FastAPI

from api.auth.router import router as auth_router
from api.conversations.router import router as conversations_router
from api.memories.router import router as memories_router


app = FastAPI(
    title="Chatbot API",
    version="1.0.0",
)


app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(memories_router)


@app.get(
    "/health",
    tags=["Health"],
)
def health():
    return {
        "status": "ok",
    }