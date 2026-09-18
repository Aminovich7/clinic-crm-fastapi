"""Regression tests for the hardening changes.

Each class here pins a specific defect that used to produce a 500, leak a
record, or leave a response unprotected.
"""

import pytest

from app.core.config import settings
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


async def _make_consultation(client, token, receipt_number=900):
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


class TestExplicitNullsAreRejected:
    """PATCH {"field": null} against a NOT NULL column was a 500."""

    @pytest.mark.parametrize(
        "payload",
        [{"amount": None}, {"type": None}, {"date": None}, {"receipt_number": None}],
    )
    async def test_null_on_a_required_field_is_422(
        self, test_client, role_tokens, payload
    ):
        record = await _make_consultation(test_client, role_tokens["manager"], 901)

        response = await test_client.patch(
            f"/consultations/{record['id']}",
            headers=auth(role_tokens["manager"]),
            json=payload,
        )
        assert response.status_code == 422, response.text

    async def test_null_on_a_nullable_field_still_clears_it(
        self, test_client, role_tokens
    ):
        record = await _make_consultation(test_client, role_tokens["manager"], 902)

        response = await test_client.patch(
            f"/consultations/{record['id']}",
            headers=auth(role_tokens["manager"]),
            json={"doctor_id": None},
        )
        assert response.status_code == 200, response.text
        assert response.json()["doctor_id"] is None

    async def test_duty_entry_null_date_is_422(self, test_client, role_tokens):
        staff = await test_client.post(
            "/staff",
            headers=auth(role_tokens["superadmin"]),
            json={"first_name": "Duty", "last_name": "Nurse", "role": "nurse", "fixed_salary": "500000"},
        )
        entry = await test_client.post(
            "/duty-entries",
            headers=auth(role_tokens["manager"]),
            json={"staff_id": staff.json()["id"], "amount": "50000"},
        )
        assert entry.status_code == 201, entry.text

        response = await test_client.patch(
            f"/duty-entries/{entry.json()['id']}",
            headers=auth(role_tokens["manager"]),
            json={"date": None},
        )
        assert response.status_code == 422


class TestVoidedRecordHandling:
    async def test_voided_record_cannot_be_edited(self, test_client, role_tokens):
        record = await _make_consultation(test_client, role_tokens["manager"], 903)
        voided = await test_client.post(
            f"/consultations/{record['id']}/void", headers=auth(role_tokens["manager"])
        )
        assert voided.status_code == 200

        response = await test_client.patch(
            f"/consultations/{record['id']}",
            headers=auth(role_tokens["manager"]),
            json={"amount": "999999"},
        )
        assert response.status_code == 409

    async def test_voided_record_is_not_returned_by_get(self, test_client, role_tokens):
        record = await _make_consultation(test_client, role_tokens["manager"], 904)
        assert (
            await test_client.get(
                f"/consultations/{record['id']}", headers=auth(role_tokens["manager"])
            )
        ).status_code == 200

        await test_client.post(
            f"/consultations/{record['id']}/void", headers=auth(role_tokens["manager"])
        )

        response = await test_client.get(
            f"/consultations/{record['id']}", headers=auth(role_tokens["manager"])
        )
        assert response.status_code == 404

    async def test_restore_still_reaches_the_voided_record(
        self, test_client, role_tokens
    ):
        """The 404 above must not break the superadmin's restore path."""
        record = await _make_consultation(test_client, role_tokens["manager"], 905)
        await test_client.post(
            f"/consultations/{record['id']}/void", headers=auth(role_tokens["manager"])
        )

        restored = await test_client.post(
            f"/consultations/{record['id']}/restore",
            headers=auth(role_tokens["superadmin"]),
        )
        assert restored.status_code == 200
        assert restored.json()["is_voided"] is False

        # ...and it is visible again afterwards.
        response = await test_client.get(
            f"/consultations/{record['id']}", headers=auth(role_tokens["manager"])
        )
        assert response.status_code == 200


class TestResponseHardening:
    async def test_security_headers_are_present(self, test_client):
        response = await test_client.get("/login")

        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "same-origin"

        csp = response.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        # The whole point of the strict policy is that there is no inline escape.
        assert "unsafe-inline" not in csp
        assert "unsafe-eval" not in csp

    async def test_security_headers_apply_to_api_responses_too(
        self, test_client, role_tokens
    ):
        response = await test_client.get("/auth/me", headers=auth(role_tokens["manager"]))
        assert response.status_code == 200
        assert "content-security-policy" in response.headers

    async def test_api_docs_are_disabled_by_default(self, test_client):
        assert settings.docs_enabled is False
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await test_client.get(path)
            assert response.status_code == 404, f"{path} -> {response.status_code}"

    async def test_health_hides_component_detail_from_anonymous_callers(
        self, test_client
    ):
        response = await test_client.get("/health")
        assert response.status_code in (200, 503)

        body = response.json()
        assert "status" in body
        assert "db" not in body
        assert "redis" not in body

    async def test_health_verbose_requires_a_valid_token(self, test_client, role_tokens):
        anonymous = await test_client.get("/health?verbose=1")
        assert "db" not in anonymous.json()

        authenticated = await test_client.get(
            "/health?verbose=1", headers=auth(role_tokens["manager"])
        )
        assert "db" in authenticated.json()
        assert "redis" in authenticated.json()
