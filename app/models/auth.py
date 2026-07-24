from pydantic import BaseModel, EmailStr

class LoginBody(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str

class MechanicLoginBody(BaseModel):
    pin: str