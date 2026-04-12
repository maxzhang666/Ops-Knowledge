from app.core.config import settings


def test_settings_loads_defaults():
    assert settings.APP_NAME == "Ops-Knowledge"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.DEBUG is False


def test_settings_has_bootstrap_fields():
    assert hasattr(settings, "DATABASE_URL")
    assert hasattr(settings, "REDIS_URL")
    assert hasattr(settings, "JWT_SECRET_KEY")


def test_settings_jwt_defaults():
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS == 7
