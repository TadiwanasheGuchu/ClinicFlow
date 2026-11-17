from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.request_context import RequestContextMiddleware
from app.modules.appointments.router import router as appointments_router
from app.modules.audit.router import router as audit_router
from app.modules.branches.router import router as branches_router
from app.modules.members.router import router as members_router
from app.modules.notifications.router import router as notifications_router
from app.modules.organisations.router import router as organisations_router
from app.modules.patients.router import router as patients_router
from app.modules.platform.router import router as platform_router
from app.modules.portal.router import router as portal_router
from app.modules.roles.router import router as roles_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.staff.router import router as staff_router
from app.modules.users.router import router as me_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
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

    return app


app = create_app()
