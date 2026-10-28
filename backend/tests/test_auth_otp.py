"""End-to-end tests for registration, login and the OTP password-reset flow.

These tests do not need MongoDB: ``auth.db_conn`` is swapped for a tiny
in-memory collection. Everything else - password hashing, JWT creation, the OTP
store, expiry, attempt limits and the three reset endpoints - is the real code.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from RapidDoc.backend.app.routers import auth


class FakeCollection:
    """The few PyMongo operations the auth router actually uses."""

    def __init__(self):
        self.docs = []

    @staticmethod
    def _matches(doc, query):
        return all(doc.get(key) == value for key, value in query.items())

    def find_one(self, query):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    def insert_one(self, doc):
        stored = dict(doc)
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    def update_one(self, query, update):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


class FakeDb:
    def __init__(self):
        self.users = FakeCollection()


@pytest.fixture
def api(monkeypatch):
    fake_db = FakeDb()
    monkeypatch.setattr(auth, "db_conn", SimpleNamespace(get_db=lambda: fake_db))
    monkeypatch.setattr(auth.settings, "OTP_RESEND_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(auth.settings, "OTP_DEV_MODE", True)

    app = FastAPI()
    app.include_router(auth.router)
    auth.otp_store.clear()

    with TestClient(app) as client:
        client.fake_db = fake_db
        yield client

    auth.otp_store.clear()


def register(client, email="student@example.com", password="OldPass123!", name="Student"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def forgot(client, email="student@example.com"):
    return client.post("/api/auth/forgot-password", json={"email": email})


def verify(client, otp, email="student@example.com"):
    return client.post("/api/auth/verify-otp", json={"email": email, "otp": otp})


def reset(client, otp, new_password, email="student@example.com"):
    return client.post(
        "/api/auth/reset-password",
        json={"email": email, "otp": otp, "new_password": new_password},
    )


def login(client, email="student@example.com", password="OldPass123!"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --------------------------------------------------------------------------
# Registration / login basics
# --------------------------------------------------------------------------

def test_register_normalizes_email_and_rejects_duplicates(api):
    res = register(api, email="  Student@Example.COM ")
    assert res.status_code == 200, res.text
    assert res.json()["email"] == "student@example.com"

    duplicate = register(api, email="student@example.com")
    assert duplicate.status_code == 400
    assert "already registered" in duplicate.json()["detail"].lower()


def test_register_rejects_short_password(api):
    res = register(api, password="123")
    assert res.status_code == 422


def test_login_and_me(api):
    register(api)

    bad = login(api, password="WrongPass1!")
    assert bad.status_code == 401
    assert "incorrect" in bad.json()["detail"].lower()

    ok = login(api)
    assert ok.status_code == 200
    token = ok.json()["access_token"]

    me = api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "student@example.com"

    anonymous = api.get("/api/auth/me")
    assert anonymous.status_code == 401


# --------------------------------------------------------------------------
# Forgot password: requesting an OTP
# --------------------------------------------------------------------------

def test_forgot_password_unknown_email_is_404(api):
    res = forgot(api, email="nobody@example.com")
    assert res.status_code == 404


def test_forgot_password_returns_dev_otp_when_no_mailer(api):
    register(api)
    res = forgot(api)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email_sent"] is False
    assert body["dev_otp"] and len(body["dev_otp"]) == 6 and body["dev_otp"].isdigit()
    assert body["expires_in"] == auth.settings.OTP_EXPIRE_MINUTES * 60


def test_forgot_password_resend_cooldown(api, monkeypatch):
    register(api)
    monkeypatch.setattr(auth.settings, "OTP_RESEND_COOLDOWN_SECONDS", 45)
    assert forgot(api).status_code == 200
    second = forgot(api)
    assert second.status_code == 429
    assert "wait" in second.json()["detail"].lower()


# --------------------------------------------------------------------------
# Verifying the OTP
# --------------------------------------------------------------------------

def test_verify_rejects_wrong_otp_and_counts_attempts(api):
    register(api)
    otp = forgot(api).json()["dev_otp"]
    wrong = "000000" if otp != "000000" else "111111"

    first = verify(api, wrong)
    assert first.status_code == 400
    assert "2 attempt" in first.json()["detail"]

    second = verify(api, wrong)
    assert second.status_code == 400
    assert "1 attempt" in second.json()["detail"]

    third = verify(api, wrong)
    assert third.status_code == 400
    assert "too many" in third.json()["detail"].lower()

    # The OTP was burned after the third failure - even the right code fails.
    after = verify(api, otp)
    assert after.status_code == 400
    assert "expired" in after.json()["detail"].lower()


def test_verify_accepts_correct_otp(api):
    register(api)
    otp = forgot(api).json()["dev_otp"]
    res = verify(api, otp)
    assert res.status_code == 200
    assert res.json()["verified"] is True


def test_verify_rejects_expired_otp(api):
    register(api)
    otp = forgot(api).json()["dev_otp"]
    auth.otp_store["student@example.com"]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    res = verify(api, otp)
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()
    assert "student@example.com" not in auth.otp_store


def test_verify_requires_existing_account(api):
    res = verify(api, "123456", email="ghost@example.com")
    assert res.status_code == 400


# --------------------------------------------------------------------------
# Resetting the password
# --------------------------------------------------------------------------

def test_reset_requires_prior_verification(api):
    register(api)
    otp = forgot(api).json()["dev_otp"]

    skipped = reset(api, otp, "NewPass123!")
    assert skipped.status_code == 400
    assert "verify" in skipped.json()["detail"].lower()

    assert verify(api, otp).status_code == 200
    done = reset(api, otp, "NewPass123!")
    assert done.status_code == 200, done.text


def test_reset_rejects_wrong_and_expired_otp(api):
    register(api)
    otp = forgot(api).json()["dev_otp"]
    verify(api, otp)

    wrong = "000000" if otp != "000000" else "111111"
    bad = reset(api, wrong, "NewPass123!")
    assert bad.status_code == 400

    auth.otp_store["student@example.com"]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    expired = reset(api, otp, "NewPass123!")
    assert expired.status_code == 400
    assert "expired" in expired.json()["detail"].lower()


def test_reset_rejects_weak_and_unchanged_passwords(api):
    register(api)
    otp = forgot(api).json()["dev_otp"]
    verify(api, otp)

    weak = reset(api, otp, "123")
    assert weak.status_code == 422

    same = reset(api, otp, "OldPass123!")
    assert same.status_code == 400
    assert "different" in same.json()["detail"].lower()


def test_full_reset_changes_password_and_burns_otp(api):
    register(api)
    otp = forgot(api).json()["dev_otp"]
    verify(api, otp)

    done = reset(api, otp, "BrandNew456!")
    assert done.status_code == 200, done.text

    # OTP is single-use.
    assert "student@example.com" not in auth.otp_store
    again = reset(api, otp, "Another789!")
    assert again.status_code == 400

    # Old password no longer works; the new one does.
    assert login(api).status_code == 401
    assert login(api, password="BrandNew456!").status_code == 200


def test_reset_unknown_email_is_rejected(api):
    res = reset(api, "123456", "NewPass123!", email="ghost@example.com")
    assert res.status_code == 400
