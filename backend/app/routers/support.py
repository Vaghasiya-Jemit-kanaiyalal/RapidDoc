"""Public support intake for the Help Center.

A support report is accepted from signed-in and signed-out visitors. When a
valid bearer token is present it is attached to the record for follow-up, but
an invalid or expired token never blocks a report.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from RapidDoc.backend.app.config import settings
from RapidDoc.backend.app.database import db_conn
from RapidDoc.backend.app.models import SupportIssueRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/support", tags=["support"])
optional_bearer = HTTPBearer(auto_error=False)


def _optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(optional_bearer),
):
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("id")
        email = payload.get("sub")
        if not user_id or not email:
            return None
        return {"id": str(user_id), "email": email}
    except JWTError:
        return None


@router.post("/issues", status_code=status.HTTP_201_CREATED)
async def create_support_issue(
    request: SupportIssueRequest,
    current_user: dict | None = Depends(_optional_user),
):
    db = db_conn.get_db()
    created_at = datetime.now(timezone.utc)
    issue = {
        "name": request.name.strip(),
        "email": str(request.email).strip().lower(),
        "category": request.category.strip() or "General question",
        "subject": request.subject.strip(),
        "message": request.message.strip(),
        "page_url": (request.page_url or "").strip() or None,
        "status": "open",
        "created_at": created_at,
        "user_id": current_user["id"] if current_user else None,
    }
    result = db.support_issues.insert_one(issue)
    ticket_id = f"RD-{created_at:%Y%m%d}-{str(result.inserted_id)[-6:].upper()}"
    logger.info("Support issue %s created for %s", ticket_id, issue["email"])
    return {
        "status": "success",
        "ticket_id": ticket_id,
        "message": "Your message was received. We will reply by email.",
    }
