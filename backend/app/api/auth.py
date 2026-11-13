from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models import User
from app.schemas.auth import (LoginRequest, PasswordChange, ProfileUpdate, RegisterRequest,
                              TokenResponse, UserOut)
from app.services.audit import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])
_AUTH_LIMIT = get_settings().auth_rate_limit

# Verified against when the email is unknown, so login timing does not reveal which emails exist.
_DUMMY_HASH = hash_password("dummy-password-1")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(_AUTH_LIMIT)
def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    # Self-registration always creates a normal user; admins are created via the CLI script.
    user = User(email=email, full_name=body.full_name, password_hash=hash_password(body.password),
                role="user")
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    log_action(db, action="auth.register", user_id=user.id, entity_type="user",
               entity_id=str(user.id), request=request)
    db.commit()
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit(_AUTH_LIMIT)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        log_action(db, action="auth.login_failed", request=request, details={"email": body.email.lower()})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    user.last_login_at = datetime.now(timezone.utc)
    log_action(db, action="auth.login", user_id=user.id, request=request)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.role), user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """JWTs are stateless: the client discards the token. This records the event for auditing."""
    log_action(db, action="auth.logout", user_id=user.id, request=request)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_profile(body: ProfileUpdate, request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.preferred_language is not None:
        user.preferred_language = body.preferred_language
    log_action(db, action="auth.profile_update", user_id=user.id, request=request)
    db.commit()
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(_AUTH_LIMIT)
def change_password(request: Request, body: PasswordChange, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    log_action(db, action="auth.password_change", user_id=user.id, request=request)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
