from dotenv import load_dotenv
load_dotenv() # Load variables from .env before initializing app

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="EDIP Suite API",
    description="Backend API for the Executive Decision Intelligence Platform",
    version="1.0.0"
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

from app.api import erp_connections, chat, health

app.include_router(erp_connections.router)
app.include_router(chat.router)
app.include_router(health.router)

