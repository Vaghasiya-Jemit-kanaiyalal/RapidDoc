"""The HTTP contract for image replacement, targeting and resizing.

The service-level tests prove the writers behave; these prove the API reports
that behaviour correctly - in particular the distinction the UI depends on:

  * 400 - the request cannot be honoured, reword or fix it and try again
  * 409 - the request is fine but *you* have to choose, so here are the options
  * 200 - it worked, and here is the state to re-render from

Mongo and the upload directory are stubbed. The files on disk are real, because
a response body is only meaningful if it describes a genuinely edited document.
"""

import io

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imagefixtures import png_bytes

USER = {"id": "user-1", "email": "user@example.com", "role": "user"}

# A real 24-hex id: the router calls ObjectId(doc_id), which rejects anything
# shorter, so a readable placeholder like "abc123" would fail every test for a
# reason that has nothing to do with the route.
DOC_ID = "0" * 24
BASE = f"/api/documents/{DOC_ID}"


class FakeCollection:
    def __init__(self, doc=None):
        self.doc = doc
        self.updates = []

    def find_one(self, query):
        return self.doc

    def update_one(self, query, update):
        self.updates.append(update)
        if "$set" in update and self.doc is not None:
            self.doc.update(update["$set"])
        return None


class FakeDb:
    def __init__(self, doc):
        self.documents = FakeCollection(doc)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient over the real router with only storage and Mongo replaced."""
    from RapidDoc.backend.app.routers import auth, documents

    state = {"db": None}

    def _save(name, data):
        # The real storage service returns an absolute path, and callers rely on
        # that (ensure_edited_version hands the return value straight to a
        # writer without resolving it again), so the stub must match.
        target = tmp_path / name
        target.write_bytes(data)
        return str(target)

    def _get_file_path(storage_path):
        return str(tmp_path / storage_path)

    def make_client(doc, source_bytes):
        # Each test owns a private copy, so edits cannot leak between tests
        # through a shared fixture file.
        stored = tmp_path / f"{doc['file_type']}-doc.{doc['file_type']}"
        stored.write_bytes(source_bytes)
        doc = dict(doc)
        doc["storage_path"] = stored.name
        state["db"] = FakeDb(doc)

        monkeypatch.setattr(documents.db_conn, "get_db", lambda: state["db"])
        monkeypatch.setattr(
            documents.storage_service, "get_file_path", _get_file_path
        )
        monkeypatch.setattr(documents.storage_service, "save_file", _save)

        app = FastAPI()
        # documents.router already carries the /api/documents prefix.
        app.include_router(documents.router)
        app.dependency_overrides[auth.get_current_user] = lambda: USER
        return TestClient(app)

    return make_client


def doc_stub(file_type):
    return {
        "_id": ObjectId(DOC_ID),
        "owner_id": "user-1",
        "file_type": file_type,
        "filename": f"sample.{file_type}",
        "storage_path": "unused",
        "edit_history": [],
    }


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


@pytest.fixture
def docx_client(client, docx_images):
    return client(doc_stub("docx"), read_bytes(docx_images))


@pytest.fixture
def pdf_client(client, pdf_images):
    return client(doc_stub("pdf"), read_bytes(pdf_images))


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_image_listing_uses_the_canonical_indexes(pdf_client):
    body = pdf_client.get(f"{BASE}/images").json()
    indexes = [img["index"] for img in body["images"]]
    assert indexes == sorted(indexes) == list(range(len(indexes)))


def test_image_listing_reports_page_numbers(pdf_client):
    body = pdf_client.get(f"{BASE}/images").json()
    assert all(img["page_num"] is not None for img in body["images"])
    assert body["images"][0]["page_num"] == 0, "stored 0-based for the client to render"


def test_image_bytes_are_served(pdf_client):
    response = pdf_client.get(f"{BASE}/images/0")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n", "must be the real PNG bytes"


def test_out_of_range_image_bytes_are_404(pdf_client):
    assert pdf_client.get(f"{BASE}/images/999").status_code == 404


def test_images_route_rejects_a_missing_document(pdf_client):
    assert pdf_client.get("/api/documents/deadbeef/images").status_code == 404


# ---------------------------------------------------------------------------
# Replacement
# ---------------------------------------------------------------------------

def test_replace_by_index(pdf_client):
    response = pdf_client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("new.png", png_bytes(300, 100), "image/png")},
        data={"image_index": "1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["replaced"] == 1
    assert "images_version" in body


def test_replace_by_page_and_ordinal(pdf_client):
    # pdf_images holds 2 images on page 1, 1 on page 2, 2 on page 3.
    response = pdf_client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("new.png", png_bytes(300, 100), "image/png")},
        data={"command": "the 2nd image on page 1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["indexes"] == [1]


def test_ambiguous_request_is_409_with_candidates(pdf_client):
    response = pdf_client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("new.png", png_bytes(300, 100), "image/png")},
        data={"command": "the image on page 1"},
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["status"] == "ambiguous"
    assert len(body["candidates"]) == 2
    assert all("label" in c for c in body["candidates"])


def test_unrecognised_wording_is_400_with_advice(pdf_client):
    response = pdf_client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("new.png", png_bytes(10, 10), "image/png")},
        data={"command": "make it nicer"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"]


def test_non_image_upload_is_400(pdf_client):
    response = pdf_client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("notes.txt", b"hello", "text/plain")},
        data={"image_index": "0"},
    )
    assert response.status_code == 400, response.text
    assert "image" in response.json()["detail"].lower()


def test_negative_index_is_400(pdf_client):
    response = pdf_client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("new.png", png_bytes(10, 10), "image/png")},
        data={"image_index": "-1"},
    )
    assert response.status_code == 400


def test_index_past_the_end_is_400_not_500(pdf_client):
    response = pdf_client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("new.png", png_bytes(10, 10), "image/png")},
        data={"image_index": "999"},
    )
    assert response.status_code == 400, response.text
    assert "does not exist" in response.json()["detail"]


def test_a_failed_replacement_leaves_the_document_readable(pdf_client):
    pdf_client.post(
        f"{BASE}/replace-image",
        files={"image_file": ("new.png", png_bytes(10, 10), "image/png")},
        data={"image_index": "999"},
    )
    assert pdf_client.get(f"{BASE}/images").status_code == 200
    assert pdf_client.get(f"{BASE}/images/0").status_code == 200


# ---------------------------------------------------------------------------
# Resolving without uploading
# ---------------------------------------------------------------------------

def test_resolve_endpoint_reports_ordinals(pdf_client):
    response = pdf_client.post(
        f"{BASE}/resolve-image",
        data={"command": "the 2nd image on page 3"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "resolved"
    assert body["indexes"] == [4]
    assert body["reason"] == "image 2 of 2 on page 3"


def test_resolve_endpoint_returns_candidates_when_ambiguous(pdf_client):
    response = pdf_client.post(
        f"{BASE}/resolve-image",
        data={"command": "the image on page 1"},
    )
    body = response.json()
    assert body["status"] == "ambiguous"
    assert len(body["candidates"]) == 2


def test_resolve_on_a_docx_never_invents_a_page(docx_client):
    response = docx_client.post(
        f"{BASE}/resolve-image",
        data={"command": "the image on page 2"},
    )
    body = response.json()
    assert body["status"] == "unresolved"
    assert "no pages" in body["message"]


# ---------------------------------------------------------------------------
# Resizing
# ---------------------------------------------------------------------------

def test_resize_by_width(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 2, "width": 2, "unit": "in"}]
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resized"] == 1
    assert body["indexes"] == [2]
    assert "->" in body["message"]


def test_resize_reports_the_new_size(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 2, "width": 2, "unit": "in"}]
    })
    width = next(
        img["width"] for img in response.json()["images"] if img["index"] == 2
    )
    assert width == pytest.approx(2 * 96, abs=2), width


def test_resize_a_batch(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={
        "items": [
            {"index": 0, "width": 1, "unit": "in"},
            {"index": 4, "height": 3, "unit": "in"},
        ]
    })
    assert response.status_code == 200, response.text
    assert response.json()["resized"] == 2


def test_resize_height_only(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 2, "height": 1, "unit": "in"}]
    })
    assert response.status_code == 200, response.text


def test_resize_of_a_shared_image_mentions_every_placement(client, pdf_same_page_twice):
    """One stored picture drawn twice: resizing it must say it touched both."""
    with open(pdf_same_page_twice, "rb") as fh:
        source = fh.read()
    c = client(doc_stub("pdf"), source)

    response = c.post(f"{BASE}/resize-image", json={
        "items": [{"index": 0, "width": 2, "unit": "in"}]
    })
    assert response.status_code == 200, response.text
    assert "2 places" in response.json()["message"], response.json()["message"]


def test_resize_rejects_an_empty_batch(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={"items": []})
    assert response.status_code == 400


def test_resize_rejects_a_negative_dimension(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 0, "width": -1, "unit": "in"}]
    })
    assert response.status_code == 422, response.text


def test_resize_rejects_an_unknown_unit(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 0, "width": 2, "unit": "parsecs"}]
    })
    assert response.status_code == 400, response.text
    assert "mm" in response.json()["detail"]


def test_resize_past_the_end_is_400_not_500(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 999, "width": 2, "unit": "in"}]
    })
    assert response.status_code == 400, response.text
    assert "does not exist" in response.json()["detail"]


def test_resize_requires_a_dimension(pdf_client):
    response = pdf_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 0}]
    })
    assert response.status_code == 400, response.text
    assert "width" in response.json()["detail"]


def test_resize_keeps_the_image_count(pdf_client):
    before = len(pdf_client.get(f"{BASE}/images").json()["images"])
    pdf_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 2, "width": 3, "unit": "in"}]
    })
    after = len(pdf_client.get(f"{BASE}/images").json()["images"])
    assert after == before


def test_resize_preserves_the_original_upload(docx_client, tmp_path):
    """The uploaded file must never be edited in place."""
    original = (tmp_path / "docx-doc.docx").read_bytes()
    docx_client.post(f"{BASE}/resize-image", json={
        "items": [{"index": 1, "width": 1, "unit": "in"}]
    })
    assert (tmp_path / "docx-doc.docx").read_bytes() == original
    assert (tmp_path / "edited.docx").exists(), "the edit went to the copy"