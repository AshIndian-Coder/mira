"""API v1 router aggregator.

Importing this package registers every route module; ``api_router`` is the
single router attached in ``app.main``.
"""
from fastapi import APIRouter

from app.api.v1.routes_auth import router as auth_router
from app.api.v1.routes_ingestion import router as ingestion_router
from app.api.v1.routes_matching import router as matching_router
from app.api.v1.routes_review import router as review_router
from app.api.v1.routes_cnmc import router as cnmc_router
from app.api.v1.routes_mapping import router as mapping_router
from app.api.v1.routes_dashboard import router as dashboard_router
from app.api.v1.routes_roi import router as roi_router
from app.api.v1.routes_audit import router as audit_router
from app.api.v1.routes_sap import router as sap_router
from app.api.v1.routes_users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(ingestion_router)
api_router.include_router(matching_router)
api_router.include_router(review_router)
api_router.include_router(cnmc_router)
api_router.include_router(mapping_router)
api_router.include_router(dashboard_router)
api_router.include_router(roi_router)
api_router.include_router(audit_router)
api_router.include_router(sap_router)
api_router.include_router(users_router)

