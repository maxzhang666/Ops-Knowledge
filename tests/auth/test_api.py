async def test_register_endpoint(client):
    resp = await client.post("/api/v1/auth/register", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "SecurePass123!",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "newuser"
    assert "id" in data
    assert "hashed_password" not in data


async def test_register_duplicate_fails(client):
    await client.post("/api/v1/auth/register", json={
        "username": "newuser", "email": "new@example.com", "password": "SecurePass123!",
    })
    resp = await client.post("/api/v1/auth/register", json={
        "username": "newuser", "email": "new2@example.com", "password": "SecurePass123!",
    })
    assert resp.status_code == 409


async def test_login_endpoint(client):
    await client.post("/api/v1/auth/register", json={
        "username": "newuser", "email": "new@example.com", "password": "SecurePass123!",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "newuser", "password": "SecurePass123!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/register", json={
        "username": "newuser", "email": "new@example.com", "password": "SecurePass123!",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "newuser", "password": "WrongPass!",
    })
    assert resp.status_code == 401


async def test_me_authenticated(client):
    await client.post("/api/v1/auth/register", json={
        "username": "newuser", "email": "new@example.com", "password": "SecurePass123!",
    })
    login = await client.post("/api/v1/auth/login", json={
        "username": "newuser", "password": "SecurePass123!",
    })
    token = login.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "newuser"


async def test_me_unauthenticated(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 403


async def test_refresh_token(client):
    await client.post("/api/v1/auth/register", json={
        "username": "newuser", "email": "new@example.com", "password": "SecurePass123!",
    })
    login = await client.post("/api/v1/auth/login", json={
        "username": "newuser", "password": "SecurePass123!",
    })
    refresh_token = login.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
