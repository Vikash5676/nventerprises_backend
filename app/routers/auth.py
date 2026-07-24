from fastapi import APIRouter, HTTPException, Depends, Response
from app.database import db
from app.models.auth import LoginBody
from app.utils.auth import verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login")
async def auth_login(body: LoginBody, response: Response):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    response.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=43200, path="/")
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}}

@router.post("/logout")
async def auth_logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

@router.get("/me")
async def auth_me(user=Depends(get_current_user)):
    return user