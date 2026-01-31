from fastapi import APIRouter
from app.api.routes.two_factor import router as two_factor_router

api_router = APIRouter()

api_router.include_router(two_factor_router, prefix="/2fa", tags=["2fa"])