"""Accounts: register, login, logout, profile, export and delete."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.errors import ApiError
from app.models import User
from app.ratelimit import auth_rate_limit
from app.schemas import DeleteAccountIn, LoginIn, ProfileUpdate, RegisterIn, UserOut
from app.security import create_session_token, hash_password, needs_rehash, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/me", tags=["account"])

_DUMMY_HASH = hash_password("timing-equaliser")   # so unknown emails cost the same as wrong passwords


def _start_session(request: Request, response: Response, user: User) -> None:
    s = request.app.state.settings
    response.set_cookie(
        s.cookie_name, create_session_token(user.id, s.secret_key, s.session_minutes),
        max_age=s.session_minutes * 60, httponly=True, secure=s.cookie_secure, samesite="lax", path="/",
    )


def _end_session(request: Request, response: Response) -> None:
    response.delete_cookie(request.app.state.settings.cookie_name, path="/")


@router.post("/register", response_model=UserOut, status_code=201, dependencies=[Depends(auth_rate_limit)])
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    user = User(email=body.email, password_hash=hash_password(body.password), display_name=body.display_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:                      # lost a race with a concurrent registration
        db.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    _start_session(request, response, user)
    return user


@router.post("/login", response_model=UserOut, dependencies=[Depends(auth_rate_limit)])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.commit()
    _start_session(request, response, user)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    _end_session(request, response)


@me_router.get("", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@me_router.patch("", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.consent_training is not None:
        user.consent_training = body.consent_training
    db.commit()
    return user


@me_router.get("/export")
def export_me(user: User = Depends(get_current_user)):
    """Everything we hold about the user (data portability). Grows as features add tables."""
    return {"user": UserOut.model_validate(user).model_dump(mode="json"), "drawings": []}


@me_router.delete("", status_code=204)
def delete_me(body: DeleteAccountIn, request: Request, response: Response,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise ApiError(403, "invalid_credentials", "Password is incorrect.")
    db.delete(user)
    db.commit()
    _end_session(request, response)
