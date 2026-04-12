import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

PROVIDER_PAYLOAD = {
    "name": "TestProvider",
    "type": "openai_compat",
    "base_url": "http://localhost:8000/v1",
    "api_key": "sk-test",
    "models_available": {"llm": ["gpt-4o"], "embedding": ["text-embedding-3-small"], "reranker": []},
    "default_llm_model": "gpt-4o",
    "default_embedding_model": "text-embedding-3-small",
}


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post("/api/v1/auth/register", json={
        "username": "modeltest", "email": "model@test.com", "password": "Test1234!",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "modeltest", "password": "Test1234!",
    })
    return resp.json()


async def _auth_headers(client: AsyncClient) -> dict:
    tokens = await _register_and_login(client)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_create_provider(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.post("/api/v1/model", json=PROVIDER_PAYLOAD, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "TestProvider"
    assert "api_key" not in data


async def test_list_providers(client: AsyncClient):
    headers = await _auth_headers(client)
    await client.post("/api/v1/model", json=PROVIDER_PAYLOAD, headers=headers)
    resp = await client.get("/api/v1/model", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_update_provider(client: AsyncClient):
    headers = await _auth_headers(client)
    create_resp = await client.post("/api/v1/model", json=PROVIDER_PAYLOAD, headers=headers)
    pid = create_resp.json()["id"]
    resp = await client.put(f"/api/v1/model/{pid}", json={"name": "Renamed"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


async def test_delete_provider(client: AsyncClient):
    headers = await _auth_headers(client)
    create_resp = await client.post("/api/v1/model", json=PROVIDER_PAYLOAD, headers=headers)
    pid = create_resp.json()["id"]
    resp = await client.delete(f"/api/v1/model/{pid}", headers=headers)
    assert resp.status_code == 204
