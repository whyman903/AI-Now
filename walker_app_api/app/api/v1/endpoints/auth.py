from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.auth import (
    authenticate_user,
    create_access_token,
    get_password_hash,
    get_current_user
)
from app.db.base import get_db
from app.db.models import User
from app.schemas.user import User as UserSchema

router = APIRouter()

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    firstName: str
    lastName: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserSchema

@router.post("/signup", response_model=TokenResponse)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    """User signup endpoint"""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists"
        )
    
    # Create new user
    hashed_password = get_password_hash(request.password)
    user = User(
        email=request.email,
        password=hashed_password,
        first_name=request.firstName,
        last_name=request.lastName,
        interests="[]",  # Empty array as string
        onboarding_completed=False
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserSchema(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            interests=user.interests,
            onboarding_completed=user.onboarding_completed,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    )

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """User login endpoint"""
    user = authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id})
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserSchema(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            interests=user.interests,
            onboarding_completed=user.onboarding_completed,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    )

@router.get("/me", response_model=UserSchema)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return UserSchema(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        interests=current_user.interests,
        onboarding_completed=current_user.onboarding_completed,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at
    )