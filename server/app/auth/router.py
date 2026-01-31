from fastapi import Depends, APIRouter
from app.auth.user import fastapi_users, auth_backend
from app.core.database.schemas import UserCreate, UserUpdate, UserRead

auth_router = APIRouter()

# Auth routers
auth_router.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
auth_router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
)
auth_router.include_router(
    fastapi_users.get_reset_password_router(), prefix="/auth", tags=["auth"]
)
auth_router.include_router(
    fastapi_users.get_verify_router(UserRead), prefix="/auth", tags=["auth"]
)
auth_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"]
)