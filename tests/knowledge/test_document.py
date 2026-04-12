"""Document upload integration tests (require running database + MinIO)."""

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
async def test_upload_document(client, auth_headers, created_kb_id):
    resp = await client.post(
        f"/knowledge/{created_kb_id}/documents",
        files={"file": ("test.txt", b"This is a test document with enough content to pass validation.", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "test.txt"
    assert data["source_type"] == "txt"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_upload_unsupported_type(client, auth_headers, created_kb_id):
    resp = await client.post(
        f"/knowledge/{created_kb_id}/documents",
        files={"file": ("binary.exe", b"some data", "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_empty_file(client, auth_headers, created_kb_id):
    resp = await client.post(
        f"/knowledge/{created_kb_id}/documents",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_documents(client, auth_headers, created_kb_id):
    resp = await client.get(
        f"/knowledge/{created_kb_id}/documents",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_get_document_not_found(client, auth_headers, created_kb_id):
    resp = await client.get(
        f"/knowledge/{created_kb_id}/documents/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404
