from datetime import datetime, timedelta, timezone
from typing import Optional
import hmac
import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from bson import ObjectId
import logging

from RapidDoc.backend.app.config import settings
from RapidDoc.backend.app.database import db_conn
from RapidDoc.backend.app.services.email_service import send_otp_email
from RapidDoc.backend.app.models import (
    UserRegister,
    UserLogin,
    UserResponse,
    Token,
    TokenData,
    ForgotPasswordRequest,
    VerifyOTPRequest,
    ResetPasswordRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# In-memory OTP store (for development; use Redis/DB in production)
# email -> {"otp", "expires_at", "attempts", "verified", "created_at"}
otp_store = {}


def _normalize_email(email: str) -> str:
    return email.lower().strip()


def _prune_expired_otps() -> None:
    now = datetime.now(timezone.utc)
    for key in [k for k, v in otp_store.items() if now > v["expires_at"]]:
        otp_store.pop(key, None)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        email: str = payload.get("sub")
        user_id: str = payload.get("id")
        if email is None or user_id is None:
            raise credentials_exception
        token_data = TokenData(email=email, user_id=user_id)
    except JWTError:
        raise credentials_exception

    try:
        db = db_conn.get_db()
        user = db.users.find_one({"_id": ObjectId(token_data.user_id)})
        if user is None:
            raise credentials_exception
        # Convert _id to string
        user["id"] = str(user["_id"])
        return user
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error in get_current_user: %s", e)
        raise credentials_exception

@router.post("/register", response_model=UserResponse)
async def register(user_data: UserRegister):
    try:
        db = db_conn.get_db()
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    # Normalize email
    email = user_data.email.lower().strip()
    
    # Check if email already exists
    existing_user = db.users.find_one({"email": email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    hashed_password = get_password_hash(user_data.password)
    
    # Create user document
    user_doc = {
        "email": email,
        "name": user_data.name.strip(),
        "hashed_password": hashed_password
    }
    
    result = db.users.insert_one(user_doc)
    
    return UserResponse(
        id=str(result.inserted_id),
        email=email,
        name=user_data.name.strip()
    )

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    try:
        db = db_conn.get_db()
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    email = user_data.email.lower().strip()
    user = db.users.find_one({"email": email})
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"], "id": str(user["_id"])},
        expires_delta=access_token_expires
    )
    
    return Token(access_token=access_token, token_type="bearer")

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        name=current_user["name"]
    )


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    try:
        db = db_conn.get_db()
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    email = _normalize_email(request.email)

    # Only registered emails can start a reset; the account must exist.
    user = db.users.find_one({"email": email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email address"
        )

    _prune_expired_otps()
    now = datetime.now(timezone.utc)

    # Simple resend cooldown so the endpoint cannot be used to spam a mailbox.
    existing = otp_store.get(email)
    if existing:
        elapsed = (now - existing["created_at"]).total_seconds()
        remaining = settings.OTP_RESEND_COOLDOWN_SECONDS - int(elapsed)
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining}s before requesting another OTP."
            )

    otp = "".join(secrets.choice(string.digits) for _ in range(6))
    expires_at = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    otp_store[email] = {
        "otp": otp,
        "expires_at": expires_at,
        "attempts": 0,
        "verified": False,
        "created_at": now,
    }

    email_sent = send_otp_email(email, otp, user.get("name"))

    # With no working mailer the OTP is surfaced for local/demo use so the
    # flow stays testable. Never expose it once email delivery succeeds.
    expose_otp = settings.OTP_DEV_MODE and not email_sent

    if not email_sent and not settings.OTP_DEV_MODE:
        del otp_store[email]
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We could not send the OTP email. Please try again later."
        )

    logger.info(
        "Password reset OTP generated for %s (emailed=%s, exposed=%s)",
        email, email_sent, expose_otp,
    )
    return {
        "message": (
            "A password reset OTP has been sent to your email address."
            if email_sent
            else "OTP generated in development mode."
        ),
        "email_sent": email_sent,
        "dev_otp": otp if expose_otp else None,
        "expires_in": settings.OTP_EXPIRE_MINUTES * 60,
    }


@router.post("/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
    try:
        db = db_conn.get_db()
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    email = _normalize_email(request.email)

    user = db.users.find_one({"email": email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or OTP"
        )

    stored = otp_store.get(email)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP. Please request a new one."
        )

    if datetime.now(timezone.utc) > stored["expires_at"]:
        del otp_store[email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one."
        )

    if stored["attempts"] >= settings.OTP_MAX_ATTEMPTS:
        del otp_store[email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many failed attempts. Please request a new OTP."
        )

    if not hmac.compare_digest(stored["otp"], request.otp):
        stored["attempts"] += 1
        left = settings.OTP_MAX_ATTEMPTS - stored["attempts"]
        if left <= 0:
            del otp_store[email]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed attempts. Please request a new OTP."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP. {left} attempt(s) remaining."
        )

    # Verified: allow exactly one password reset with this code.
    stored["verified"] = True
    stored["attempts"] = 0
    otp_store[email] = stored

    return {"message": "OTP verified successfully", "verified": True}


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    try:
        db = db_conn.get_db()
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    email = _normalize_email(request.email)

    user = db.users.find_one({"email": email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset request."
        )

    stored = otp_store.get(email)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP. Please start again."
        )

    if datetime.now(timezone.utc) > stored["expires_at"]:
        del otp_store[email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please start again."
        )

    if stored["attempts"] >= settings.OTP_MAX_ATTEMPTS:
        del otp_store[email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many failed attempts. Please request a new OTP."
        )

    if not hmac.compare_digest(stored["otp"], request.otp):
        stored["attempts"] += 1
        otp_store[email] = stored
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP."
        )

    # The OTP must have passed /verify-otp first.
    if not stored.get("verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please verify the OTP before resetting your password."
        )

    # Refuse to reuse the current password so a reset is a real change.
    if verify_password(request.new_password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your new password must be different from your current password."
        )

    hashed_password = get_password_hash(request.new_password)
    db.users.update_one(
        {"email": email},
        {"$set": {"hashed_password": hashed_password}}
    )

    # Single-use: burn the OTP after a successful reset.
    otp_store.pop(email, None)

    logger.info("Password reset completed for %s", email)
    return {"message": "Password reset successfully. You can now log in."}

