"""Email + password auth with opaque session tokens in an HttpOnly cookie.

Passwords are hashed with scrypt (stdlib). Only a SHA-256 of each session token is
stored, so a leaked database can't be replayed as live sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AuthSession, User

COOKIE = "hs_session"
SESSION_DAYS = 30


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(dk.hex(), digest)


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(token_hash=_th(token), user_id=user.id, expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS))
    )
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == _th(token)).delete()
        db.commit()
    response.delete_cookie(COOKIE, path="/")


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    s = db.get(AuthSession, _th(token))
    if not s:
        return None
    exp = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        db.delete(s)
        db.commit()
        return None
    return db.get(User, s.user_id)


def current_user(user: User | None = Depends(optional_user)) -> User:
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


class RateLimiter:
    """Small in-memory sliding-window limiter (per process) for auth endpoints."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window = limit, window
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.time()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")
        q.append(now)


auth_limiter = RateLimiter(limit=10, window=60)
