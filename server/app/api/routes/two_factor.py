from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.auth.user import get_jwt_strategy, get_user_manager, cookie_transport, fastapi_users as ftu
from app.core.two_factor import otp_utils

router = APIRouter(tags=["two_factor"])

class OTPVerification(BaseModel):
    otp: str
    email: str

@router.post("/verify")
async def verify(request: OTPVerification, manager = Depends(get_user_manager)):
    try:
        if otp_utils.verify_otp(request.otp, request.email):
            # manager = ftu.get_user_manager()
            user = await manager.get_by_email(request.email)
            token = await get_jwt_strategy().write_token(user)
            response = await cookie_transport.get_login_response(token)
            return response
        else:
            return Response(status_code=401)

    except Exception as error:
        raise HTTPException(500, "Error in verifying otp")
