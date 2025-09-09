from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class User(UserBase):
    id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    interests: str
    onboarding_completed: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True