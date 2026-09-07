from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-driven cross-CPSE material harmonization backend",
)

app.include_router(api_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "mira-backend",
    }
