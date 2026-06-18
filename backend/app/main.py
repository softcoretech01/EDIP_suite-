from dotenv import load_dotenv
load_dotenv() # Load variables from .env before initializing app

import asyncio
import os
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _warmup_ollama():
    """Send a tiny prompt to Ollama so the model is loaded into RAM before the first real query."""
    model = os.getenv("OLLAMA_MODEL", "qwen2.5").strip().strip('"').strip("'")
    try:
        requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": "hi", "stream": False, "options": {"num_predict": 1}},
            timeout=60,
        )
        print(f"[startup] Ollama model '{model}' warmed up successfully.")
    except Exception as e:
        print(f"[startup] Ollama warm-up skipped: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    def _init_db():
        try:
            from app.database.database import Base, engine
            Base.metadata.create_all(bind=engine)
            print("[startup] Database tables verified/created.")
        except Exception as e:
            print(f"[startup] WARNING: Database connection failed. Tables could not be created/verified: {e}")

    loop = asyncio.get_event_loop()
    # Run DB init in a background thread so it doesn't block startup if the DB is slow/down
    loop.run_in_executor(None, _init_db)

    # Warm up Ollama in a background thread so it doesn't block the server from starting
    loop.run_in_executor(None, _warmup_ollama)
    yield


app = FastAPI(
    title="EDIP Suite API",
    description="Backend API for the Executive Decision Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to EDIP Suite API"}

from app.api import erp_connections, chat, health, auth_api, uploads

app.include_router(auth_api.router)
app.include_router(erp_connections.router)
app.include_router(chat.router)
app.include_router(health.router)
app.include_router(uploads.router)


# Trigger reload 3
