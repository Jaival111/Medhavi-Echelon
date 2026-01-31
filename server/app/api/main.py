from fastapi import APIRouter
from app.api.routes.two_factor import router as two_factor_router
from app.api.routes.chat import router as chat_router

api_router = APIRouter()

api_router.include_router(two_factor_router, prefix="/2fa", tags=["2fa"])
api_router.include_router(chat_router, tags=["chat"])