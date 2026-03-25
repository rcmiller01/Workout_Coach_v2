"""
AI Fitness Coach — Auth Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class SetPasswordRequest(BaseModel):
    username: str
    password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True
