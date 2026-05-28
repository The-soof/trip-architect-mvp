from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.models import TravelerProfile, User
from app.schemas.auth import UserCreate


def get_user_by_email(db: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email.lower())
    return db.scalar(statement)


def create_user(db: Session, payload: UserCreate) -> User:
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name.strip(),
        hashed_password=get_password_hash(payload.password),
    )
    db.add(user)
    db.flush()
    profile = TravelerProfile(user_id=user.id, interests=[])
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

