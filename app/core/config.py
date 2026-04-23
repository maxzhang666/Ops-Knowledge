import os

from pydantic_settings import BaseSettings

# Disable LangChain / LangSmith tracing at import time.
# LangGraph (used by the workflow engine, see Plan 29) imports ``langchain_core``
# transitively; its default tracer would POST to LangSmith unless we opt out.
# Our observability goes through Langfuse, emitted manually from
# ``app/model/service.py`` and node adapters. ``setdefault`` lets tests /
# deployments override if needed, but the default is OFF.
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


class Settings(BaseSettings):
    APP_NAME: str = "Ops-Knowledge"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Bootstrap config (from .env)
    DATABASE_URL: str = "postgresql+asyncpg://opsknowledge:opsknowledge@localhost:5432/ops_knowledge"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"

    # JWT defaults
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Milvus (default for local dev, production via SystemSettings UI)
    MILVUS_URI: str = "http://localhost:19530"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"  # comma-separated origins

    # MinIO (default for local dev)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "ops-knowledge-docs"
    MINIO_SECURE: bool = False

    # ``extra="ignore"`` tolerates deprecated env vars (e.g. WORKFLOW_ENGINE
    # removed after Plan 29) — avoids forcing every dev to clean their .env.
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
