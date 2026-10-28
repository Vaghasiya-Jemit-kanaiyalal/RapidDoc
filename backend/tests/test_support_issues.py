"""Help Center support intake.

The route is intentionally public: a signed-out visitor can still report an
issue. These tests replace Mongo with a small in-memory collection so they stay
offline and verify the stored record and ticket format.
"""

from types import SimpleNamespace

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from RapidDoc.backend.app.routers import support


class FakeSupportCollection:
    def __init__(self):
        self.documents = []

    def insert_one(self, document):
        self.documents.append(document)
        return SimpleNamespace(inserted_id=ObjectId("64b000000000000000000001"))


@pytest.fixture()
def client(monkeypatch):
    collection = FakeSupportCollection()
    fake_db = SimpleNamespace(support_issues=collection)
    monkeypatch.setattr(support.db_conn, "get_db", lambda: fake_db)
    app = FastAPI()
    app.include_router(support.router)
    return TestClient(app), collection


def test_support_issue_is_stored_with_ticket_id(client):
    test_client, collection = client
    response = test_client.post(
        "/api/support/issues",
        json={
            "name": "Asha Patel",
            "email": "ASHA@example.com",
            "category": "Bug report",
            "subject": "Replace skipped a table cell",
            "message": "The command replaced paragraph text but not the table cell.",
            "page_url": "http://localhost:5173/#workspace",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ticket_id"].startswith("RD-")
    assert len(collection.documents) == 1
    stored = collection.documents[0]
    assert stored["email"] == "asha@example.com"
    assert stored["category"] == "Bug report"
    assert stored["status"] == "open"
    assert stored["user_id"] is None


def test_support_issue_rejects_short_message(client):
    test_client, collection = client
    response = test_client.post(
        "/api/support/issues",
        json={
            "name": "Asha Patel",
            "email": "asha@example.com",
            "subject": "Help",
            "message": "too short",
        },
    )

    assert response.status_code == 422
    assert collection.documents == []
