from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    audit,
    mappings,
    matching,
    materials,
    review,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(materials.router)
api_router.include_router(matching.router)
api_router.include_router(review.router)
api_router.include_router(audit.router)
api_router.include_router(analytics.router)
api_router.include_router(mappings.router)
