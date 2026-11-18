from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from app.core.database import engine, Base
from app import models
from app.routers import (
    users, admin, conversations, ai, documents, knowledge, programs,
    applicants, handoffs, students, schedules, payments, attendance,
    student_requests, appointments,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not models.__all__:
        raise RuntimeError("Application models are not loaded")
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Concierge API", description="Academy AI Assistant", version="1.0.0", lifespan=lifespan)
for router_module in [users, admin, conversations, ai, documents, knowledge, programs,
                      applicants, handoffs, students, schedules, payments, attendance,
                      student_requests, appointments]:
    app.include_router(router_module.router)

@app.get("/")
def home(): return {"message": "Welcome to Concierge API", "status": "running"}

@app.get("/health")
def health_check(): return {"status": "healthy"}

@app.get("/health/db")
def database_health():
    with engine.connect() as connection: connection.execute(text("SELECT 1"))
    return {"database": "connected", "status": "healthy"}
