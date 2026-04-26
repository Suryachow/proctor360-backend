from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    device_hash: str
    live_image_base64: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_hash: str


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
