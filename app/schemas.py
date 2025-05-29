
# app/schemas.py
from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import List, Optional
from datetime import date
from .models import SubscriptionStatusEnum

# --- Plan Schemas ---
class PlanBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    price: float = Field(..., ge=0) # Greater than or equal to 0
    features: Optional[str] = None
    duration_days: int = Field(..., gt=0)

class PlanCreate(PlanBase):
    pass

class Plan(PlanBase):
    id: int
    class Config:
        from_attributes = True

# --- User Schemas ---
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr # Pydantic will validate if it's a valid email format

class UserCreate(UserBase):
    """
    Why this Pydantic model is necessary:
    - Validates incoming data for creating a new user, including their plain-text password.
    What it's doing:
    - Inherits `username` and `email` from `UserBase`.
    - Adds a `password` field. This password will be hashed before storing.
    """
    password: str = Field(..., min_length=8)

class User(UserBase): # Schema for returning User data (without password)
    """
    Why this Pydantic model is necessary:
    - Defines the structure for returning user data in API responses.
    - Importantly, it does NOT include the password (or hashed_password) for security.
    What it's doing:
    - Includes `id`, `username`, and `email`.
    """
    id: int
    class Config:
        from_attributes = True

# --- Token Schemas ---
class Token(BaseModel):
    """
    Why this Pydantic model is necessary:
    - Defines the structure of the response when a user successfully logs in.
    What it's doing:
    - `access_token`: The JWT string.
    - `token_type`: Usually "bearer".
    """
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """
    Why this Pydantic model is necessary:
    - Defines the expected structure of the data embedded within the JWT payload.
    What it's doing:
    - `username`: Stores the username of the authenticated user. Can be None.
    """
    username: Optional[str] = None

# --- Subscription Schemas ---
class SubscriptionBase(BaseModel):
    user_id: int # This will usually be derived from the authenticated user
    plan_id: int

class SubscriptionCreate(BaseModel): # Client only sends plan_id; user_id comes from token
    """
    Why this Pydantic model is necessary:
    - Validates incoming data for creating a new subscription.
    - Note: `user_id` is no longer directly provided by the client in the request body
      for this endpoint; it will be derived from the authenticated user's JWT.
    What it's doing:
    - Specifies `plan_id` as the required field.
    """
    plan_id: int = Field(..., gt=0)

class SubscriptionUpdate(BaseModel):
    new_plan_id: int = Field(..., gt=0)

class Subscription(SubscriptionBase):
    id: int
    start_date: date
    end_date: date
    status: SubscriptionStatusEnum
    plan: Plan
    user_id: int # Keep user_id here for response consistency

    class Config:
        from_attributes = True
        use_enum_values = True
