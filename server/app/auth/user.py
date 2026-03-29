import uuid
from typing import Optional
from fastapi import Depends, Request, HTTPException
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy, CookieTransport, Strategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

from app.models.UserModel import User
from app.core.database.user import get_user_db
from app.core.config import SECRET, COOKIE_SECURE, COOKIE_SAMESITE
from app.core.two_factor.otp_utils import get_otp
from app.core.email import email

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(self, user: User, token: str, request: Optional[Request] = None):
        print(f"User {user.id} has forgot password. Reset token: {token}")

    async def on_after_request_verify(self, user: User, token: str, request: Optional[Request] = None):
        print(f"Verification requested for user {user.id}. Token: {token}")

async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)

cookie_transport = CookieTransport(
        cookie_name="user_cookie",
        cookie_max_age=3600,  # 1 hour
        cookie_secure=COOKIE_SECURE,
        cookie_httponly=True,
        cookie_samesite=COOKIE_SAMESITE,
    )

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

class AuthBackend(AuthenticationBackend):
    async def login(self, strategy: Strategy[models.UP, models.ID], user: models.UP):
        try:
            otp = get_otp(user.email)

            receiver = user.email
            subject = "OTP Verification"
            message = "<p> Your One-Time Password is : {otp} </p>".format(otp=otp)

            await email.send_email(receiver, subject, message)
            return {"message": "OTP Verification Sent"}

        except Exception as error:
            print(error)
            raise HTTPException(500, "Error in generating otp")

auth_backend = AuthBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)  # For protected routes