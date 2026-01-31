from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from typing import Literal

from app.auth.user import get_jwt_strategy, get_user_manager, cookie_transport, fastapi_users as ftu
from app.core.two_factor import otp_utils

router = APIRouter(tags=["two_factor"])

class OTPVerification(BaseModel):
    otp: str
    email: str
    mode: Literal["login", "signup"] = "login"

@router.post("/verify")
async def verify(request: OTPVerification, manager = Depends(get_user_manager)):
    try:
        if not otp_utils.verify_otp(request.otp, request.email):
            return Response(status_code=401)

        user = await manager.get_by_email(request.email)
        if request.mode == "signup" and not user.is_verified:
            await manager.user_db.update(user, {"is_verified": True})

        token = await get_jwt_strategy().write_token(user)
        response = await cookie_transport.get_login_response(token)
        return response

    except Exception:
        raise HTTPException(500, "Error in verifying otp")
