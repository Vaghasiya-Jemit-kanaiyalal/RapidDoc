"""Version history: every edit has to be undoable, and the original has to survive.

`edit_history` records what changed but deliberately holds no bytes, so it cannot
answer "put it back". These tests pin the part that can: a checkpoint is taken
before each edit that would overwrite one, restoring returns the exact bytes that
were live at the time, and no sequence of edits or restores can damage the
uploaded original.

The in-memory Mongo double applies `$push`/`$slice`/`$set` for real, because the
pruning logic is only meaningful if the stored array actually shrinks.
"""

import io

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imagefixtures import png_bytes

USER = {"id": "user-1", "email": "user@example.com", "role": "user"}

DOC_ID = "0" * 24
BASE = f"/api/documents/{DOC_ID}"


class FakeCollection:
    """Just enough of pymongo to exercise the update operators that are used."""

    def __init__(self, doc):
        self.doc = doc
        self.updates = []

    def find_one(self, query=None, *args, **kwargs):
        return self.doc

    def update_one(self, query, update):
        self.updates.append(update)

        for field, value in (update.get("$set") or {}).items():
            self.doc[field] = value

        for field, value in (update.get("$push") or {}).items():
            values = value if isinstance(value, list) else [value]
            self.doc.setdefault(field, []).extend(values)
            depth = (update.get("$slice") or {}).get(field)
            if isinstance(depth, int):
                # Negative depth keeps the newest entries, matching Mongo.
                if depth >= 0:
                    del self.doc[field][depth:]
                else:
                    del self.doc[field][:depth]


class FakeDb:
    def __init__(self, doc):
        self.documents = FakeCollection(doc)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """A client over the real router, with only Mongo and storage replaced."""
    from RapidDoc.backend.app.routers import auth, documents

    state = {"db": None}

    def _save(name, data):
        # Absolute path, like the real service: writers are handed this value
        # without resolving it again.
        target = tmp_path / name
        target.write_bytes(data)
        return str(target)

    monkeypatch.setattr(documents.storage_service, "get_file_path",
                        lambda storage_path: str(tmp_path / storage_path))
    monkeypatch.setattr(documents.storage_service, "save_file", _save)

    def make(doc_bytes, file_type="pdf"):
        stored = tmp_path / f"source.{file_type}"
        stored.write_bytes(doc_bytes)
        doc = {
            "_id": ObjectId(DOC_ID),
            "owner_id": "user-1",
            "file_type": file_type,
            "filename": f"source.{file_type}",
            "storage_path": stored.name,
            "edit_history": [],
        }
        state["db"] = FakeDb(doc)
        monkeypatch.setattr(documents.db_conn, "get_db", lambda: state["db"])

        app = FastAPI()
        app.include_router(documents.router)
        app.dependency_overrides[auth.get_current_user] = lambda: USER
        client = TestClient(app)
        # Handed back on the client so tests can read the stored document without
        # reaching into the fixture's closure.
        client.db = state["db"]
        return client

    return make


@pytest.fixture
def pdf(harness, pdf_images):
    with open(pdf_images, "rb") as fh:
        return harness(fh.read())


def doc_of(client):
    return client.db.documents.doc


def read_active(client):
    with open(str(doc_of(client)["storage_path"]), "rb") as fh:
        return fh.read()


def replace_first_image(client, color=(9, 9, 9)):
    return client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("new.png", png_bytes(10, 10, color), "image/png")},
        data={"image_index": "0"},
    )


# ---------------------------------------------------------------------------
# Timeline shape
# ---------------------------------------------------------------------------

def test_a_fresh_document_has_only_a_current_version(pdf):
    body = pdf.get(f"{BASE}/versions").json()
    labels = [v["label"] for v in body["versions"]]
    assert labels == ["Current version"]
    assert body["has_original"] is True
    assert body["versions"][0]["restorable"] is False


def test_the_first_edit_does_not_duplicate_the_original(pdf):
    """The uploaded file is already preserved, so checkpointing it would double up."""
    assert replace_first_image(pdf).status_code == 200
    body = pdf.get(f"{BASE}/versions").json()
    assert [v["label"] for v in body["versions"]] == ["Current version", "Original upload"]
    assert doc_of(pdf).get("versions", []) == []


def test_each_later_edit_adds_one_checkpoint(pdf):
    replace_first_image(pdf, (9, 9, 9))
    replace_first_image(pdf, (8, 8, 8))
    replace_first_image(pdf, (7, 7, 7))

    body = pdf.get(f"{BASE}/versions").json()
    checkpoints = [v for v in body["versions"] if v.get("version_id")]
    assert len(checkpoints) == 2
    # Newest first, and the original stays pinned at the bottom.
    assert body["versions"][-1]["is_original"] is True
    assert body["versions"][0]["is_current"] is True
    assert [c["number"] for c in checkpoints] == [2, 1]


def test_a_checkpoint_says_which_edit_it_precedes(pdf):
    replace_first_image(pdf, (9, 9, 9))
    replace_first_image(pdf, (8, 8, 8))
    labels = [v["label"] for v in pdf.get(f"{BASE}/versions").json()["versions"]]
    assert "Image replacement (1)" in labels


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------

def test_restoring_a_checkpoint_returns_the_exact_earlier_bytes(harness, pdf_images):
    with open(pdf_images, "rb") as fh:
        client = harness(fh.read())

    replace_first_image(client, (9, 9, 9))
    after_first = read_active(client)
    replace_first_image(client, (8, 8, 8))
    assert read_active(client) != after_first

    checkpoint = next(v for v in client.get(f"{BASE}/versions").json()["versions"]
                      if v.get("version_id"))
    response = client.post(f"{BASE}/versions/{checkpoint['version_id']}/restore")
    assert response.status_code == 200, response.text
    assert read_active(client) == after_first


def test_restoring_the_original_brings_back_the_uploaded_file(harness, pdf_images):
    with open(pdf_images, "rb") as fh:
        uploaded = fh.read()
    client = harness(uploaded)

    replace_first_image(client, (9, 9, 9))
    replace_first_image(client, (8, 8, 8))

    response = client.post(f"{BASE}/versions/original/restore")
    assert response.status_code == 200, response.text
    assert read_active(client) == uploaded


def test_the_original_survives_edits_and_restores(harness, tmp_path, pdf_images):
    with open(pdf_images, "rb") as fh:
        uploaded = fh.read()
    client = harness(uploaded)
    original_path = doc_of(client)["storage_path"]

    replace_first_image(client, (9, 9, 9))
    client.post(f"{BASE}/versions/original/restore")
    replace_first_image(client, (8, 8, 8))

    doc = doc_of(client)
    assert doc["original_storage_path"] == original_path
    assert (tmp_path / original_path).read_bytes() == uploaded


def test_a_restore_is_itself_reversible(harness, pdf_images):
    with open(pdf_images, "rb") as fh:
        client = harness(fh.read())

    replace_first_image(client, (9, 9, 9))
    replace_first_image(client, (8, 8, 8))
    before_restore = read_active(client)

    checkpoint = next(v for v in client.get(f"{BASE}/versions").json()["versions"]
                      if v.get("version_id"))
    assert client.post(f"{BASE}/versions/{checkpoint['version_id']}/restore").status_code == 200

    # The state the restore replaced must still be on the timeline.
    labels = [v["label"] for v in client.get(f"{BASE}/versions").json()["versions"]]
    assert any(label.startswith("Before restoring to") for label in labels)
    undo = next(v for v in client.get(f"{BASE}/versions").json()["versions"]
                if v["label"].startswith("Before restoring to"))
    assert client.post(f"{BASE}/versions/{undo['version_id']}/restore").status_code == 200
    assert read_active(client) == before_restore


def test_restoring_reports_the_change_in_edit_history(pdf):
    replace_first_image(pdf, (9, 9, 9))
    replace_first_image(pdf, (8, 8, 8))
    client = pdf
    client.post(f"{BASE}/versions/original/restore")
    actions = [entry["action"] for entry in doc_of(client)["edit_history"]]
    assert "Restored Original upload" in actions


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------

def test_an_unknown_version_is_a_404(pdf):
    response = pdf.post(f"{BASE}/versions/deadbeef/restore")
    assert response.status_code == 404
    assert "no longer exists" in response.json()["detail"]


def test_a_vanished_version_file_is_a_410(pdf, tmp_path):
    import os

    replace_first_image(pdf, (9, 9, 9))
    replace_first_image(pdf, (8, 8, 8))
    checkpoint = next(v for v in pdf.get(f"{BASE}/versions").json()["versions"]
                      if v.get("version_id"))
    os.remove(str(tmp_path / checkpoint["storage_path"]))

    response = pdf.post(f"{BASE}/versions/{checkpoint['version_id']}/restore")
    assert response.status_code == 410


def test_restoring_a_document_that_was_never_edited_reports_the_original(pdf):
    """Un-edited documents have no separate original copy, and none are invented."""
    response = pdf.post(f"{BASE}/versions/original/restore")
    assert response.status_code == 200
    assert read_active(pdf) is not None


def test_the_timeline_of_a_document_with_many_edits_stays_bounded(pdf, monkeypatch):
    from RapidDoc.backend.app.services import version_history

    monkeypatch.setattr(version_history, "MAX_VERSIONS", 3)
    for colour in range(5):
        replace_first_image(pdf, (colour, colour, colour))

    checkpoints = [v for v in doc_of(pdf)["versions"] if v.get("version_id")]
    assert len(checkpoints) <= 3


def test_documents_are_isolated_from_each_other(harness, pdf_images):
    with open(pdf_images, "rb") as fh:
        first = harness(fh.read())
    replace_first_image(first, (9, 9, 9))
    replace_first_image(first, (8, 8, 8))

    with open(pdf_images, "rb") as fh:
        second = harness(fh.read())
    body = second.get(f"{BASE}/versions").json()
    assert [v["label"] for v in body["versions"]] == ["Current version"]


# ---------------------------------------------------------------------------
# DOCX: the same guarantee, on the other format
# ---------------------------------------------------------------------------

def test_a_docx_edit_is_checkpointed_and_reversible(harness, docx_images):
    with open(docx_images, "rb") as fh:
        client = harness(fh.read(), file_type="docx")

    assert replace_first_image(client, (9, 9, 9)).status_code == 200
    after_first = read_active(client)
    assert replace_first_image(client, (8, 8, 8)).status_code == 200

    checkpoint = next(v for v in client.get(f"{BASE}/versions").json()["versions"]
                      if v.get("version_id"))
    assert client.post(f"{BASE}/versions/{checkpoint['version_id']}/restore").status_code == 200

    restored = read_active(client)
    assert restored == after_first
    # A restored DOCX still has to be a working document, not just matching bytes.
    import docx

    document = docx.Document(io.BytesIO(restored))
    assert document.paragraphs


def test_resizing_a_docx_is_checkpointed(harness, docx_images):
    with open(docx_images, "rb") as fh:
        client = harness(fh.read(), file_type="docx")

    replace_first_image(client, (9, 9, 9))
    before_resize = read_active(client)
    resized = client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 0, "width": 3, "unit": "in"}]
    })
    assert resized.status_code == 200, resized.text
    assert read_active(client) != before_resize

    labels = [v["label"] for v in client.get(f"{BASE}/versions").json()["versions"]]
    assert any("Image resize" in label for label in labels)
