"""KB CRUD integration tests (require running database)."""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def base_url():
    return "http://test/api/v1"


@pytest_asyncio.fixture
async def client(base_url):
    async with AsyncClient(transport=ASGITransport(app=app), base_url=base_url) as c:
        yield c


@pytest.mark.asyncio
async def test_create_kb(client, auth_headers):
    resp = await client.post(
        "/knowledge",
        json={"name": "Test KB", "description": "A test knowledge base"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test KB"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_kbs(client, auth_headers):
    resp = await client.get("/knowledge", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_kb_not_found(client, auth_headers):
    resp = await client.get(f"/knowledge/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_kb(client, auth_headers, created_kb_id):
    resp = await client.put(
        f"/knowledge/{created_kb_id}",
        json={"name": "Updated KB"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated KB"


@pytest.mark.asyncio
async def test_delete_kb(client, auth_headers, created_kb_id):
    resp = await client.delete(f"/knowledge/{created_kb_id}", headers=auth_headers)
    assert resp.status_code == 202
