from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)


@app.get(f"{settings.API_V1_PREFIX}/health")
async def health_placeholder():
    return {"status": "ok"}
