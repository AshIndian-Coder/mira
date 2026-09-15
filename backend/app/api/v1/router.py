"""API v1 router - mounts all route handlers under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import routes_auth, routes_ingestion, routes_matching, routes_review
from app.api.v1 import routes_cnmc, routes_mapping, routes_dashboard, routes_roi
from app.api.v1 import routes_audit, routes_sap, routes_users

api_v1 = APIRouter()

api_v1.include_router(routes_auth.router)
api_v1.include_router(routes_ingestion.router)
api_v1.include_router(routes_matching.router)
api_v1.include_router(routes_review.router)
api_v1.include_router(routes_cnmc.router)
api_v1.include_router(routes_mapping.router)
api_v1.include_router(routes_dashboard.router)
api_v1.include_router(routes_roi.router)
api_v1.include_router(routes_audit.router)
api_v1.include_router(routes_sap.router)
api_v1.include_router(routes_users.router)
