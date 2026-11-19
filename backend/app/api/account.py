from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..auth import auth_limiter, current_user, end_session, hash_password, start_session, verify_password
from ..db import get_db
from ..models import User
from ..pipeline.captions import PRESETS
from ..schemas import BrandKitIn, LoginIn, SignupIn
from ..serializers import user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limiter.check(f"signup:{request.client.host if request.client else '?'}")
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists. Try signing in.")
    user = User(
        email=email,
        name=body.name.strip() or email.split("@")[0],
        password_hash=hash_password(body.password),
        brand_kit={},
    )
    db.add(user)
    db.commit()
    start_session(db, user, response)
    return user_out(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limiter.check(f"login:{request.client.host if request.client else '?'}:{body.email.lower()}")
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    start_session(db, user, response)
    return user_out(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    end_session(db, request, response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.put("/brand-kit")
def brand_kit(body: BrandKitIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    kit = dict(u.brand_kit or {})
    if body.caption_preset is not None:
        if body.caption_preset and body.caption_preset not in PRESETS:
            raise HTTPException(422, "Unknown caption preset.")
        kit["caption_preset"] = body.caption_preset or None
    if body.caption_style is not None:
        kit["caption_style"] = {k: v for k, v in body.caption_style.items() if k in PRESETS["bold_creator"]}
    if body.watermark is not None:
        kit["watermark"] = body.watermark.strip()
    if body.name is not None:
        u.name = body.name.strip()
    if body.socials is not None:
        allowed = ("youtube", "tiktok", "instagram", "linkedin", "facebook", "x")
        kit["socials"] = {k: str(v).strip()[:200] for k, v in body.socials.items() if k in allowed and str(v).strip()}
    if body.timezone is not None:
        kit["timezone"] = body.timezone.strip() or None
    u.brand_kit = kit
    db.commit()
    return user_out(u)
