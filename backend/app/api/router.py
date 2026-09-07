from fastapi import APIRouter

from app.api.routes import matching


api_router = APIRouter(prefix="/api")

api_router.include_router(matching.router)
