from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.database import engine, Base
from app import models
from app.routers import (
    users, admin, conversations, ai, documents, knowledge, programs,
    applicants, handoffs, students, schedules, payments, attendance,
    student_requests, appointments, email_assistant, messaging_integrations,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not models.__all__:
        raise RuntimeError("Application models are not loaded")
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Concierge API", description="Academy AI Assistant", version="1.0.0", lifespan=lifespan)

cast(Any, app).add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router_module in [users, admin, conversations, ai, documents, knowledge, programs,
                      applicants, handoffs, students, schedules, payments, attendance,
                      student_requests, appointments, email_assistant, messaging_integrations]:
    app.include_router(router_module.router)

@app.get("/")
def home(): return {"message": "Welcome to Concierge API", "status": "running"}

@app.get("/health")
def health_check(): return {"status": "healthy"}

@app.get("/health/db")
def database_health():
    with engine.connect() as connection: connection.execute(text("SELECT 1"))
    return {"database": "connected", "status": "healthy"}
