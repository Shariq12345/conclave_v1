from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class UserRegister(BaseModel):
    username: str
    org_name: str
    email: str
    full_name: str
    password: str
    role: Optional[str] = "Operator"


class UserLogin(BaseModel):
    username_or_email: str
    password: str


@router.post("/register")
def register(data: UserRegister):
    service = ServiceRegistry().auth_service
    user = service.register(
        username=data.username,
        org_name=data.org_name,
        email=data.email,
        full_name=data.full_name,
        password=data.password,
        role=data.role or "Operator",
    )
    return user.to_dict()


@router.post("/login")
def login(data: UserLogin):
    service = ServiceRegistry().auth_service
    token = service.login(
        username_or_email=data.username_or_email,
        password=data.password,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/whoami")
def whoami(current_user=Depends(get_current_user)):
    """Return the full profile of the currently authenticated user."""
    service = ServiceRegistry().user_service
    user = service.get_user(current_user.username)
    return user.to_dict()


@router.get("/ca-cert")
def get_ca_cert():
    """Return the server's Root CA certificate PEM string (public endpoint)."""
    import os
    from conclave.server.pki import CONCLAVE_DIR
    ca_cert_path = os.path.join(CONCLAVE_DIR, "ca_cert.pem")
    if os.path.exists(ca_cert_path):
        with open(ca_cert_path, "r") as f:
            return {"ca_cert": f.read()}
    
    from conclave.server.pki import get_or_create_ca
    _, ca_cert = get_or_create_ca()
    from cryptography.hazmat.primitives import serialization
    return {"ca_cert": ca_cert.public_bytes(serialization.Encoding.PEM).decode()}

