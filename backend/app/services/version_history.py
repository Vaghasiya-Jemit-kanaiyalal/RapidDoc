"""Snapshotted document versions, so an edit can be taken back.

`edit_history` already answers "what did I change?" but it deliberately holds no
file bytes, so it cannot answer "put it back". Every rewrite used to overwrite
the active document in place; once that happened the previous state was gone for
good. This module keeps a copy of the state a change is about to replace, which
makes each edit individually reversible and the original upload reachable through
the same UI.

Storage is a copy per version rather than a diff: documents here are small, and a
plain copy cannot drift out of sync with the metadata the way a patch can.
"""

import logging
import uuid
from datetime import datetime

from RapidDoc.backend.app.services.storage import storage_service

logger = logging.getLogger(__name__)

# Old versions fall off the end rather than growing without bound. Well past what
# anyone scrolls back through, and bounded so a long editing session cannot fill
# the disk with full copies of every intermediate state.
MAX_VERSIONS = 40


def _file_type(doc: dict) -> str:
    return doc.get("file_type") or "docx"


def _read(storage_path: str) -> bytes:
    with open(storage_service.get_file_path(storage_path), "rb") as fh:
        return fh.read()


def _store(doc: dict, prefix: str, data: bytes) -> str:
    return storage_service.save_file(f"{prefix}.{_file_type(doc)}", data)


def snapshot_version(db, doc: dict, action: str) -> dict | None:
    """Copy the document's current state aside before an edit overwrites it.

    Returns the stored entry, or ``None`` when there is nothing worth keeping.
    The very first edit is skipped on purpose: the state it would capture is the
    uploaded original, which `original_storage_path` already preserves, and
    duplicating it would put the same bytes in the timeline twice.

    `action` describes the change about to run, so the entry reads as
    "the document as it was before X".
    """
    if not doc.get("original_storage_path"):
        return None

    versions = list(doc.get("versions") or [])
    number = len(versions) + 1

    data = _read(doc["storage_path"])
    storage_path = _store(doc, f"v{number}", data)

    entry = {
        "version_id": uuid.uuid4().hex[:12],
        "number": number,
        "storage_path": storage_path,
        "label": action,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "size": len(data),
        "file_type": _file_type(doc),
        "is_original": False,
    }

    update: dict = {"$push": {"versions": entry}}
    if len(versions) >= MAX_VERSIONS:
        # Trim the oldest checkpoint in the same write, then delete its bytes.
        # Pushing and slicing in one update avoids a window where the array is
        # longer than the prune believes.
        oldest = versions[0]
        update = {
            "$push": {"versions": entry},
            "$slice": {"versions": -(MAX_VERSIONS - 1)},
        }
    db.documents.update_one({"_id": doc["_id"]}, update)

    if len(versions) >= MAX_VERSIONS:
        storage_service.delete_file(oldest["storage_path"])

    return entry


def list_versions(doc: dict) -> list:
    """The timeline, newest first, with the live document at the top.

    The active file is included as an un-restorable entry because it is the state
    the user is looking at and the obvious thing to label "current"; it has no
    stored copy of its own, which is exactly why it is marked rather than listed
    as restorable.
    """
    timeline = [{
        "version_id": None,
        "number": None,
        "label": "Current version",
        "created_at": None,
        "size": _safe_size(doc.get("storage_path")),
        "file_type": _file_type(doc),
        "is_original": False,
        "is_current": True,
        "restorable": False,
    }]

    versions = list(doc.get("versions") or [])
    for entry in reversed(versions):
        timeline.append({
            **entry,
            "is_current": False,
            "restorable": True,
        })

    # The original upload is always reachable once there is something to go back
    # to. Before the first edit it *is* the live file, so listing it separately
    # would offer the user two names for the same bytes.
    if doc.get("has_edited_version"):
        original_path = doc.get("original_storage_path") or doc.get("storage_path")
        if original_path:
            timeline.append({
                "version_id": None,
                "number": None,
                "storage_path": original_path,
                "label": "Original upload",
                "created_at": None,
                "size": _safe_size(original_path),
                "file_type": _file_type(doc),
                "is_original": True,
                "is_current": False,
                "restorable": True,
            })

    return timeline


def find_version(doc: dict, version_id: str) -> dict:
    """The restorable entry behind a timeline id, or raise ValueError.

    The original upload is addressed as ``"original"`` because it has no id of
    its own; every checkpoint has a real one.
    """
    if version_id == "original":
        original_path = doc.get("original_storage_path") or (
            None if doc.get("has_edited_version") else doc.get("storage_path")
        )
        if not original_path:
            raise ValueError("This document has no preserved original to restore.")
        return {"version_id": "original", "storage_path": original_path, "label": "Original upload"}

    for entry in doc.get("versions") or []:
        if entry.get("version_id") == version_id:
            return entry

    raise ValueError("That version no longer exists.")


def restore_version(db, doc: dict, version_id: str) -> str:
    """Make an older version the active document; returns the new storage path.

    The state being replaced is snapshotted first, so a restore is itself
    undoable rather than a one-way trip.
    """
    entry = find_version(doc, version_id)
    data = _read(entry["storage_path"])

    snapshot_version(db, doc, f"Before restoring to {entry.get('label') or 'an earlier version'}")

    return _store(doc, "restored", data)


def _safe_size(storage_path: str | None) -> int | None:
    if not storage_path:
        return None
    try:
        return len(_read(storage_path))
    except Exception as e:  # a missing file must not break the timeline
        logger.warning("Could not stat version file %s: %s", storage_path, e)
        return None