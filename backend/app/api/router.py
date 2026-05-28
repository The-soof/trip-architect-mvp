from fastapi import APIRouter

from app.api import auth, profile, trips

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(trips.router)
