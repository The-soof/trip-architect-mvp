from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import TravelerProfile, User
from app.schemas.profile import TravelerProfileRead, TravelerProfileUpdate

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=TravelerProfileRead)
def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TravelerProfileRead:
    profile = current_user.profile or TravelerProfile(user_id=current_user.id, interests=[])
    if profile.id is None:
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return TravelerProfileRead.model_validate(profile)


@router.put("/me", response_model=TravelerProfileRead)
def update_profile(
    payload: TravelerProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TravelerProfileRead:
    profile = current_user.profile or TravelerProfile(user_id=current_user.id, interests=[])
    if profile.id is None:
        db.add(profile)
        db.flush()
    profile.home_airport = payload.home_airport.strip().upper() if payload.home_airport else None
    profile.budget_preference = payload.budget_preference
    profile.pace_preference = payload.pace_preference
    profile.interests = [interest.strip() for interest in payload.interests if interest.strip()]
    db.commit()
    db.refresh(profile)
    return TravelerProfileRead.model_validate(profile)

