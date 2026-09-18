"""HTTP-level tests for authentication and role enforcement.

Everything else in this suite calls the service layer directly, which means
the application's central security properties — that a token is required,
that roles are enforced, that an assistant sees only their own records —
were never actually exercised. These tests go through the ASGI app so the
dependency chain (`get_current_user` -> `require_roles` -> endpoint) runs for
real.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


# Endpoints each role must NOT reach, as (method, path).
MANAGER_ONLY = [
    ("GET", "/duty-entries"),
    ("GET", "/expenses"),
    ("GET", "/expenses/summary"),
    ("GET", "/pharmacy/entries"),
    ("GET", "/pharmacy/summary"),
    ("GET", "/salary/payments"),
    ("GET", "/salary/balance"),
    ("GET", "/salary/total-paid"),
    ("GET", "/reports/consultations"),
    ("GET", "/reports/surgeries"),
    ("GET", "/reports/rooms"),
    ("GET", "/staff"),
    ("GET", "/users/assistants"),
]

SUPERADMIN_ONLY = [
    ("GET", "/voided-records"),
    ("GET", "/admin/settings/finance"),
    ("GET", "/users/managers"),
]


class TestAuthenticationRequired:
    async def test_protected_endpoint_rejects_anonymous(self, test_client):
        response = await test_client.get("/auth/me")
        assert response.status_code == 401

    async def test_protected_endpoint_rejects_garbage_token(self, test_client):
        response = await test_client.get("/auth/me", headers=auth("not-a-jwt"))
        assert response.status_code == 401

    async def test_token_signed_with_wrong_key_is_rejected(self, test_client, seeded_db):
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "superadmin",
                "ver": 0,
                "type": "access",
                "jti": str(uuid.uuid4()),
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            },
            "definitely-not-the-real-signing-key",
            algorithm=settings.jwt_algorithm,
        )
        response = await test_client.get("/auth/me", headers=auth(forged))
        assert response.status_code == 401

    async def test_non_uuid_subject_is_401_not_500(self, test_client, seeded_db):
        """Regression: uuid.UUID(sub) raised ValueError and surfaced as a 500."""
        token = jwt.encode(
            {
                "sub": "i-am-not-a-uuid",
                "role": "superadmin",
                "ver": 0,
                "type": "access",
                "jti": str(uuid.uuid4()),
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        response = await test_client.get("/auth/me", headers=auth(token))
        assert response.status_code == 401

    async def test_refresh_token_is_not_accepted_as_access_token(
        self, test_client, seeded_db
    ):
        login = await test_client.post(
            "/auth/login",
            data={
                "username": settings.superadmin_username,
                "password": settings.superadmin_password,
            },
        )
        refresh = login.json()["refresh_token"]

        response = await test_client.get("/auth/me", headers=auth(refresh))
        assert response.status_code == 401

    async def test_expired_token_is_rejected(self, test_client, seeded_db):
        expired = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "superadmin",
                "ver": 0,
                "type": "access",
                "jti": str(uuid.uuid4()),
                "iat": datetime.now(timezone.utc) - timedelta(hours=2),
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        response = await test_client.get("/auth/me", headers=auth(expired))
        assert response.status_code == 401


class TestRoleEnforcement:
    @pytest.mark.parametrize("method,path", MANAGER_ONLY)
    async def test_assistant_is_forbidden(self, test_client, role_tokens, method, path):
        response = await test_client.request(
            method, path, headers=auth(role_tokens["assistant"])
        )
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"

    @pytest.mark.parametrize("method,path", SUPERADMIN_ONLY)
    async def test_manager_is_forbidden(self, test_client, role_tokens, method, path):
        response = await test_client.request(
            method, path, headers=auth(role_tokens["manager"])
        )
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"

    @pytest.mark.parametrize("method,path", MANAGER_ONLY + SUPERADMIN_ONLY)
    async def test_superadmin_is_allowed(self, test_client, role_tokens, method, path):
        response = await test_client.request(
            method, path, headers=auth(role_tokens["superadmin"])
        )
        assert response.status_code == 200, f"{method} {path} -> {response.text}"

    async def test_manager_cannot_create_a_manager(self, test_client, role_tokens):
        response = await test_client.post(
            "/users/managers",
            headers=auth(role_tokens["manager"]),
            json={"username": "sneaky", "full_name": "Sneaky Manager", "password": "pw-12345678"},
        )
        assert response.status_code == 403

    async def test_manager_cannot_update_another_manager(self, test_client, role_tokens):
        other = await test_client.post(
            "/users/managers",
            headers=auth(role_tokens["superadmin"]),
            json={"username": "other-manager", "full_name": "Other Manager", "password": "pw-12345678"},
        )
        other_id = other.json()["id"]

        response = await test_client.patch(
            f"/users/managers/{other_id}",
            headers=auth(role_tokens["manager"]),
            json={"username": "hijacked", "full_name": "Hijacked", "password": "pw-12345678"},
        )
        assert response.status_code == 403

    async def test_assistant_staff_options_are_forced_to_doctors(
        self, test_client, role_tokens
    ):
        await test_client.post(
            "/staff",
            headers=auth(role_tokens["superadmin"]),
            json={"first_name": "Nurse", "last_name": "Person", "role": "nurse", "fixed_salary": "1000000"},
        )
        await test_client.post(
            "/staff",
            headers=auth(role_tokens["superadmin"]),
            json={"first_name": "Doc", "last_name": "Person", "role": "doctor", "specialty": "Cardio"},
        )

        # Asking for nurses explicitly must still come back doctors-only.
        response = await test_client.get(
            "/staff/options?role=nurse", headers=auth(role_tokens["assistant"])
        )
        assert response.status_code == 200
        assert {option["role"] for option in response.json()} <= {"doctor"}


class TestAssistantOwnership:
    async def _make_consultation(self, client, token, receipt_number):
        response = await client.post(
            "/consultations",
            headers=auth(token),
            json={
                "type": "korik",
                "receipt_number": receipt_number,
                "amount": "100000",
                "doctor_percent": "50",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    async def test_assistant_cannot_read_another_users_record(
        self, test_client, role_tokens
    ):
        managers_record = await self._make_consultation(
            test_client, role_tokens["manager"], 501
        )

        response = await test_client.get(
            f"/consultations/{managers_record['id']}",
            headers=auth(role_tokens["assistant"]),
        )
        assert response.status_code == 403

    async def test_assistant_list_excludes_other_users_records(
        self, test_client, role_tokens
    ):
        await self._make_consultation(test_client, role_tokens["manager"], 502)
        mine = await self._make_consultation(test_client, role_tokens["assistant"], 503)

        response = await test_client.get(
            "/consultations", headers=auth(role_tokens["assistant"])
        )
        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert ids == [mine["id"]]

    async def test_assistant_total_report_counts_only_their_own(
        self, test_client, role_tokens
    ):
        await self._make_consultation(test_client, role_tokens["manager"], 504)
        await self._make_consultation(test_client, role_tokens["assistant"], 505)

        response = await test_client.get(
            "/reports/total", headers=auth(role_tokens["assistant"])
        )
        assert response.status_code == 200
        # Exactly one 100000 consultation, theirs — not the manager's as well.
        assert response.json()["total_income"] == "100000"

    async def test_assistant_cannot_edit_even_their_own_record(
        self, test_client, role_tokens
    ):
        mine = await self._make_consultation(test_client, role_tokens["assistant"], 506)

        response = await test_client.patch(
            f"/consultations/{mine['id']}",
            headers=auth(role_tokens["assistant"]),
            json={"amount": "1"},
        )
        assert response.status_code == 403


class TestSessionInvalidation:
    async def test_blocking_a_user_invalidates_their_existing_token(
        self, test_client, role_tokens
    ):
        assistant_token = role_tokens["assistant"]
        assert (await test_client.get("/auth/me", headers=auth(assistant_token))).status_code == 200

        listed = await test_client.get(
            "/users/assistants", headers=auth(role_tokens["superadmin"])
        )
        assistant_id = listed.json()["items"][0]["id"]

        blocked = await test_client.post(
            f"/users/assistants/{assistant_id}/block",
            headers=auth(role_tokens["superadmin"]),
        )
        assert blocked.status_code == 200

        response = await test_client.get("/auth/me", headers=auth(assistant_token))
        assert response.status_code == 401

    async def test_logout_blocklists_the_access_token(self, test_client, role_tokens):
        token = role_tokens["manager"]
        assert (await test_client.get("/auth/me", headers=auth(token))).status_code == 200

        logged_out = await test_client.post("/auth/logout", headers=auth(token))
        assert logged_out.status_code == 204

        response = await test_client.get("/auth/me", headers=auth(token))
        assert response.status_code == 401


class TestCredentialRules:
    async def test_short_superadmin_password_is_rejected(self, test_client, role_tokens):
        response = await test_client.patch(
            "/users/superadmin",
            headers=auth(role_tokens["superadmin"]),
            json={"superadmin_password": "short"},
        )
        assert response.status_code == 422

    async def test_renaming_onto_a_taken_username_is_409_not_500(
        self, test_client, role_tokens
    ):
        listed = await test_client.get(
            "/users/assistants", headers=auth(role_tokens["superadmin"])
        )
        assistant_id = listed.json()["items"][0]["id"]

        response = await test_client.patch(
            f"/users/assistants/{assistant_id}",
            headers=auth(role_tokens["superadmin"]),
            json={
                "username": "test-manager",  # already taken
                "full_name": "Test Assistant",
                "password": "assistant-pw-123",
            },
        )
        assert response.status_code == 409
