from datetime import UTC, datetime, timedelta

from tests.conftest import OTHER_KEY, make_token


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_requires_authentication(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_rejects_token_signed_by_unknown_key(client):
    token = make_token("sub-x", "x@example.com", key=OTHER_KEY)
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_rejects_expired_token(client):
    token = make_token("sub-x", "x@example.com", exp=datetime.now(UTC) - timedelta(hours=1))
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_rejects_wrong_issuer_and_audience(client):
    for override in ({"iss": "https://evil.test"}, {"aud": "another-api"}):
        token = make_token("sub-x", "x@example.com", **override)
        response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, override


def test_unverified_email_is_refused(client):
    token = make_token("sub-unverified", "u@example.com", email_verified=False)
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_unverified"


def test_first_sign_in_creates_user(new_actor):
    actor = new_actor("Ndapewa Test")
    response = actor.get("/api/v1/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == actor.email
    assert body["full_name"] == "Ndapewa Test"
    assert body["memberships"] == []
    assert body["is_platform_admin"] is False


def test_email_cannot_be_claimed_by_second_identity(new_actor, client):
    actor = new_actor()
    assert actor.get("/api/v1/me").status_code == 200
    token = make_token("different-sub", actor.email)
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_conflict"


def test_request_id_is_propagated(client, new_actor):
    actor = new_actor()
    response = client.get("/api/v1/me", headers={**actor.headers(), "X-Request-ID": "trace-123"})
    assert response.headers["x-request-id"] == "trace-123"
