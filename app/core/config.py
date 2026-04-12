from pydantic_settings import BaseSettings


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

    # MinIO (default for local dev)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "ops-knowledge-docs"
    MINIO_SECURE: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
