"""Central FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import (
    client_payments,
    clients,
    contracts,
    finance_reports,
    holidays,
    line_system_config,
    matches,
    orders,
    payments,
    schedule,
    staff,
    staff_payments,
)
from api.schemas.base import BaseResponse
from line.line_bot import router as line_router
from line.worker import start_worker, stop_worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker_task = start_worker()
    try:
        yield
    finally:
        await stop_worker(worker_task)


app = FastAPI(
    title="Labor Union Webhook & API",
    description="LINE, LIFF, BreezySign and labor union administration API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="line/static"), name="static")

# LINE/LIFF/webhook endpoints are a child router of this central application.
app.include_router(line_router)

# Existing administration API routers.
app.include_router(orders.router)
app.include_router(matches.router)
app.include_router(schedule.router)
app.include_router(payments.router)
app.include_router(clients.router)
app.include_router(staff.router)
app.include_router(holidays.router)
app.include_router(line_system_config.router)
app.include_router(client_payments.router)
app.include_router(staff_payments.router)
app.include_router(contracts.router)
app.include_router(finance_reports.router)


@app.get("/health", response_model=BaseResponse[dict], tags=["Health"])
def api_health_check():
    return BaseResponse(
        data={"status": "healthy", "service": "Labor Union API"},
        message="API Server is running normally",
    )
