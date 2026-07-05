import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional

SECRET_KEY = "conclave-super-secret-key-change-in-prod"
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    """
    Securely hash a password using bcrypt.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a bcrypt hash.
    """
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta_seconds: int = 3600) -> str:
    """
    Generate a signed JWT access token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=expires_delta_seconds)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return {}
