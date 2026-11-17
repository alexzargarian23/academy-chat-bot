
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import engine, Base
from app import models

from app.routers import (
    users,
    admin,
    conversations,
    ai,
    documents,
    knowledge,
    programs,
    applicants,
    handoffs,
    students,
    schedules,
    payments,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Concierge API",
    description="Academy AI Assistant",
    version="1.0.0",
    lifespan=lifespan
)


app.include_router(users.router)
app.include_router(admin.router)
app.include_router(conversations.router)
app.include_router(ai.router)
app.include_router(documents.router)
app.include_router(knowledge.router)
app.include_router(programs.router)
app.include_router(applicants.router)
app.include_router(handoffs.router)
app.include_router(students.router)
app.include_router(schedules.router)
app.include_router(payments.router)


@app.get("/")
def home():
    return {
        "message": "Welcome to Concierge API",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/health/db")
def database_health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "database": "connected",
        "status": "healthy"
    }
