import pytest

from app.auth.schemas import UserCreate
from app.auth.service import AuthService


async def test_register_user(db_session):
    svc = AuthService(db_session)
    user = await svc.register(UserCreate(
        username="testuser", email="test@example.com", password="SecurePass123!"
    ))
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.hashed_password != "SecurePass123!"


async def test_register_duplicate_username_fails(db_session):
    svc = AuthService(db_session)
    await svc.register(UserCreate(
        username="testuser", email="test1@example.com", password="SecurePass123!"
    ))
    with pytest.raises(ValueError, match="already exists"):
        await svc.register(UserCreate(
            username="testuser", email="test2@example.com", password="SecurePass123!"
        ))


async def test_authenticate_valid(db_session):
    svc = AuthService(db_session)
    await svc.register(UserCreate(
        username="testuser", email="test@example.com", password="SecurePass123!"
    ))
    user = await svc.authenticate("testuser", "SecurePass123!")
    assert user is not None
    assert user.username == "testuser"


async def test_authenticate_wrong_password(db_session):
    svc = AuthService(db_session)
    await svc.register(UserCreate(
        username="testuser", email="test@example.com", password="SecurePass123!"
    ))
    user = await svc.authenticate("testuser", "WrongPassword!")
    assert user is None


async def test_create_and_verify_tokens(db_session):
    svc = AuthService(db_session)
    user = await svc.register(UserCreate(
        username="testuser", email="test@example.com", password="SecurePass123!"
    ))
    tokens = svc.create_tokens(user)
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"

    payload = svc.verify_token(tokens["access_token"])
    assert payload is not None
    assert payload["sub"] == str(user.id)
    assert payload["role"] == "user"


async def test_verify_invalid_token(db_session):
    svc = AuthService(db_session)
    assert svc.verify_token("invalid.token.here") is None
