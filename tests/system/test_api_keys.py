from app.auth.schemas import UserCreate
from app.auth.service import AuthService
from app.system.schemas import ApiKeyCreate
from app.system.service import ApiKeyService


async def test_create_api_key(db_session):
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="testuser", email="test@example.com", password="SecurePass123!"))
    svc = ApiKeyService(db_session)
    api_key, raw_key = await svc.create_key(user.id, ApiKeyCreate(name="test-key"))
    assert raw_key.startswith("sk-")
    assert api_key.key_prefix == raw_key[:8]
    assert api_key.is_active is True


async def test_verify_valid_key(db_session):
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="testuser", email="test@example.com", password="SecurePass123!"))
    svc = ApiKeyService(db_session)
    _, raw_key = await svc.create_key(user.id, ApiKeyCreate(name="test-key"))
    verified = await svc.verify_key(raw_key)
    assert verified is not None


async def test_verify_invalid_key(db_session):
    svc = ApiKeyService(db_session)
    verified = await svc.verify_key("sk-invalid-key")
    assert verified is None


async def test_revoke_key(db_session):
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="testuser", email="test@example.com", password="SecurePass123!"))
    svc = ApiKeyService(db_session)
    api_key, raw_key = await svc.create_key(user.id, ApiKeyCreate(name="test-key"))
    await svc.revoke_key(api_key.id, user.id)
    verified = await svc.verify_key(raw_key)
    assert verified is None


async def test_list_keys(db_session):
    auth_svc = AuthService(db_session)
    user = await auth_svc.register(UserCreate(username="testuser", email="test@example.com", password="SecurePass123!"))
    svc = ApiKeyService(db_session)
    await svc.create_key(user.id, ApiKeyCreate(name="key-1"))
    await svc.create_key(user.id, ApiKeyCreate(name="key-2"))
    keys = await svc.list_keys(user.id)
    assert len(keys) == 2
