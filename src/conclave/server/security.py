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


# ── TOTP (MFA) Implementation ────────────────────────────────────────────────
import base64
import os
import hmac
import hashlib
import struct
import time

def generate_mfa_secret() -> str:
    """Generates a random Base32 TOTP secret key."""
    return base64.b32encode(os.urandom(10)).decode("utf-8")

def get_totp_token(secret: str, intervals_no: int) -> str:
    """Generates a standard 6-digit TOTP code for a specific interval."""
    secret = secret.strip()
    missing_padding = len(secret) % 8
    if missing_padding:
        secret += "=" * (8 - missing_padding)
    
    key = base64.b32decode(secret, casefold=True)
    msg = struct.pack(">Q", intervals_no)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[19] & 15
    token_int = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
    return f"{token_int:06d}"

def verify_totp_token(secret: str, code: str) -> bool:
    """Verifies a user-provided code against a TOTP secret (allowing +/- 30s skew)."""
    if not secret or not code:
        return False
    code = code.replace(" ", "").replace("-", "")
    if not code.isdigit() or len(code) != 6:
        return False

    current_interval = int(time.time()) // 30
    # Allow code drift of 1 time-step (30 seconds) in either direction
    for offset in (-1, 0, 1):
        if get_totp_token(secret, current_interval + offset) == code:
            return True
    return False


# ── Resend Email Integration ─────────────────────────────────────────────────
import requests

def send_resend_email(to_email: str, subject: str, html_content: str) -> bool:
    """Sends email via the Resend API. Falls back to console printing if key is missing."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print(f"[Resend Mock Email] To: {to_email} | Subject: {subject}")
        print(f"[Resend Mock Email] Body: {html_content}")
        return True

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": "Conclave Security <onboarding@resend.dev>",
        "to": to_email,
        "subject": subject,
        "html": html_content
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            return True
        else:
            print(f"[Resend API Error] Status {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"[Resend Exception] Connection failed: {e}")
        return False


# ── In-Memory Rate Limiting ──────────────────────────────────────────────────
from collections import defaultdict
from fastapi import HTTPException, Request

class InMemoryRateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def is_rate_limited(self, ip: str, path: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        key = (ip, path)
        # Filter request history within the active window
        self.requests[key] = [t for t in self.requests[key] if now - t < window_seconds]
        if len(self.requests[key]) >= limit:
            return True
        self.requests[key].append(now)
        return False

rate_limiter = InMemoryRateLimiter()

def rate_limit(limit: int, window_seconds: int):
    """FastAPI Dependency for request rate limiting. Bypassed in TESTING mode."""
    def dependency(request: Request):
        if os.getenv("TESTING") == "true" or os.getenv("BYPASS_AUTH") == "true":
            return
        client_ip = request.client.host if request.client else "127.0.0.1"
        path = request.url.path
        if rate_limiter.is_rate_limited(client_ip, path, limit, window_seconds):
            raise HTTPException(
                status_code=429, 
                detail="Too many requests. Please try again later."
            )
    return dependency

