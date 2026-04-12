import pytest
from pydantic import ValidationError

from app.auth.schemas import UserCreate, UserResponse


def test_user_create_valid():
    user = UserCreate(username="testuser", email="test@example.com", password="SecurePass123!")
    assert user.username == "testuser"
    assert user.email == "test@example.com"


def test_user_create_short_password_fails():
    with pytest.raises(ValidationError):
        UserCreate(username="testuser", email="test@example.com", password="short")


def test_user_create_invalid_email_fails():
    with pytest.raises(ValidationError):
        UserCreate(username="testuser", email="not-an-email", password="SecurePass123!")


def test_user_create_short_username_fails():
    with pytest.raises(ValidationError):
        UserCreate(username="ab", email="test@example.com", password="SecurePass123!")


def test_user_response_excludes_sensitive_fields():
    fields = UserResponse.model_fields
    assert "hashed_password" not in fields
    assert "password" not in fields
    assert "id" in fields
    assert "username" in fields
    assert "role" in fields
