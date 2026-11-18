import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.exceptions import register_exception_handlers
from app.core.request_context import RequestContextMiddleware
from app.modules.appointments.router import router as appointments_router
from app.modules.audit.router import router as audit_router
from app.modules.billing.router import router as billing_router
from app.modules.branches.router import router as branches_router
from app.modules.clinical.router import router as clinical_router
from app.modules.dental.router import router as dental_router
from app.modules.inventory.router import router as inventory_router
from app.modules.laboratory.router import router as laboratory_router
from app.modules.medical_aid.router import router as medical_aid_router
from app.modules.members.router import router as members_router
from app.modules.notifications.router import router as notifications_router
from app.modules.organisations.router import router as organisations_router
from app.modules.patients.router import router as patients_router
from app.modules.physio.router import router as physio_router
from app.modules.platform.router import router as platform_router
from app.modules.portal.router import router as portal_router
from app.modules.reports.router import router as reports_router
from app.modules.roles.router import router as roles_router
from app.modules.roster.router import router as roster_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.staff.router import router as staff_router
from app.modules.users.router import router as me_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Optionally run the notification worker in-process (single-service hosting)."""
    stop = threading.Event()
    thread = None
    if get_settings().run_worker_in_api:
        from app.worker import run

        thread = threading.Thread(target=run, args=(15.0, stop), name="notifications", daemon=True)
        thread.start()
    yield
    stop.set()
    if thread is not None:
        thread.join(timeout=5)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title="ClinicFlow API",
        version="0.1.0",
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "production" else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Organisation-Id", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for router in (
        me_router,
        organisations_router,
        branches_router,
        roles_router,
        members_router,
        staff_router,
        patients_router,
        scheduling_router,
        appointments_router,
        clinical_router,
        laboratory_router,
        inventory_router,
        roster_router,
        dental_router,
        physio_router,
        billing_router,
        medical_aid_router,
        reports_router,
        notifications_router,
        portal_router,
        audit_router,
        platform_router,
    ):
        api.include_router(router)
    app.include_router(api)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def ready() -> JSONResponse:
        """Readiness: the database answers. No data is read."""
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "database unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
