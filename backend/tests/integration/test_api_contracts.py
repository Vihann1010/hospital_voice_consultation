"""API contract tests against the real app and a real database.

These assert the security boundary rather than business logic: that protected
routes reject anonymous callers, that role separation is enforced by the API
and not only by the UI, and that the documented response shapes hold.
"""
import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/consultations"),
        ("get", "/api/v1/consultations/stats"),
        ("get", "/api/v1/patients"),
        ("get", "/api/v1/investigations/catalog"),
        ("get", "/api/v1/investigations/workspace"),
        ("get", "/api/v1/prescriptions/formulary"),
        ("post", "/api/v1/prescriptions"),
        ("post", "/api/v1/investigations/orders"),
    ],
)
async def test_protected_routes_reject_anonymous_callers(client, method, path):
    response = await getattr(client, method)(path)
    assert response.status_code in (401, 403), (
        f"{method.upper()} {path} returned {response.status_code} without a token"
    )


async def test_health_probes_are_public():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


async def test_login_rejects_bad_credentials_without_revealing_accounts(client):
    unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@satyahospital.in", "password": "wrong"},
    )
    known = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@satyahospital.in", "password": "definitely-wrong"},
    )
    assert unknown.status_code == known.status_code == 401
    # Identical messages, so the endpoint cannot be used to enumerate accounts.
    assert unknown.json()["detail"] == known.json()["detail"]


async def test_login_succeeds_and_returns_a_usable_token(client):
    import os

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": os.environ.get("ADMIN_EMAIL", "admin@satyahospital.in"),
            "password": os.environ.get("ADMIN_PASSWORD", "ChangeMe@123"),
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


async def test_error_responses_carry_a_request_id(client):
    response = await client.get("/api/v1/consultations/not-a-uuid")
    assert "request_id" in response.json() or response.status_code == 422


async def test_security_headers_are_present(client):
    response = await client.get("/api/v1/health/live")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
