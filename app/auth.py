# app/auth.py
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from dotenv import load_dotenv

from . import schemas, models, crud # We'll need crud to fetch user for login
from .database import get_db # To get a DB session in get_current_user
from sqlalchemy.orm import Session


load_dotenv()

# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
"""
Why pwd_context is necessary:
- Manages password hashing and verification using secure algorithms like bcrypt.
What it's doing:
- Configures passlib to use bcrypt for hashing.
"""

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your_fallback_secret_key_please_change_in_env") # Load from .env or use a default
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)) # Load from .env or default to 30

if SECRET_KEY == "your_fallback_secret_key_please_change_in_env":
    print("WARNING: Using fallback JWT_SECRET_KEY. Please set a strong, unique key in your .env file!")
"""
Why SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES are necessary:
- SECRET_KEY: A secret string used to sign and verify JWTs. Keep it very secret!
- ALGORITHM: The cryptographic algorithm used for signing (HS256 is common).
- ACCESS_TOKEN_EXPIRE_MINUTES: How long a token is valid after being issued.
"""

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
"""
Why oauth2_scheme is necessary:
- It's a FastAPI utility that tells FastAPI how to find the token in the request
  (usually in the 'Authorization: Bearer <token>' header).
- tokenUrl="token": Specifies the URL endpoint where clients can go to get a token (our login endpoint).
"""

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Why this function is necessary:
    - To securely compare a plain-text password (provided during login) with a stored hashed password.
    What it's doing:
    - Uses pwd_context to check if the plain password, when hashed, matches the stored hash.
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Why this function is necessary:
    - To securely hash a plain-text password before storing it in the database.
    What it's doing:
    - Uses pwd_context to generate a bcrypt hash of the password.
    """
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Why this function is necessary:
    - To generate a new JWT access token.
    What it's doing:
    - Takes data to be encoded in the token (e.g., username).
    - Sets an expiration time for the token.
    - Encodes the data and expiration time into a JWT string, signed with SECRET_KEY.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db) # Added db session
) -> models.User:
    """
    Why this function is necessary:
    - This is a FastAPI dependency that will be used to protect endpoints.
    - It extracts, decodes, and validates the JWT from the request.
    - If valid, it fetches and returns the user associated with the token.
    What it's doing:
    1. Tries to decode the JWT using SECRET_KEY and ALGORITHM.
    2. Extracts the username from the token's payload.
    3. If decoding fails or username is missing, raises an authentication error.
    4. Fetches the user from the database based on the username.
    5. If user not found, raises an authentication error.
    6. Returns the User ORM object.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub") # "sub" is a standard claim for subject (username)
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db, username=token_data.username) # We need this CRUD function
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """
    Why this function is necessary:
    - An additional check on top of get_current_user, for instance, to ensure the user is "active"
      if you had an `is_active` flag in your User model. For now, it just returns the user.
    What it's doing:
    - (Currently) Simply returns the user obtained from get_current_user.
    - Could be extended to check user.is_active or other status flags.
    """
    # If you add an `is_active` field to your User model, you can check it here:
    # if not current_user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user