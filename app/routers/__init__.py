"""
Routers Package
==============

FastAPI routers that expose the hidden Python API modules as HTTP endpoints.
"""

from app.routers.calendar import router as calendar_router
from app.routers.auth import router as auth_router
from app.routers.tax_health import router as tax_health_router
from app.routers.notices import router as notices_router
from app.routers.documents import router as documents_router
from app.routers.invoices import router as invoices_router
from app.routers.verify import router as verify_router
from app.routers.monitor import router as monitor_router
from app.routers.team import router as team_router
from app.routers.workspaces import router as workspaces_router
from app.routers.uploads import router as uploads_router
from app.routers.assistant import router as assistant_router
from app.routers.vault import router as vault_router

__all__ = [
    "auth_router",
    "calendar_router",
    "tax_health_router",
    "notices_router",
    "documents_router",
    "invoices_router",
    "verify_router",
    "monitor_router",
    "team_router",
    "workspaces_router",
    "uploads_router",
    "assistant_router",
    "vault_router",
]
