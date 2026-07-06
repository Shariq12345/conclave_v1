from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import get_current_user
from conclave.server.security import rate_limit

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Request Schemas ───────────────────────────────────────────────────────────

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


class ForgotPassword(BaseModel):
    email_or_username: str


class ResetPassword(BaseModel):
    token: str
    new_password: str


class MFAConfirm(BaseModel):
    secret: str
    code: str


class MFADisable(BaseModel):
    code: str


class LoginMFA(BaseModel):
    mfa_token: str
    code: str


# ── Endpoint Routes ───────────────────────────────────────────────────────────

@router.post("/register")
def register(data: UserRegister, request: Request, rate_lim=Depends(rate_limit(5, 60))):
    """Register a new user account. Rate-limited to 5 requests per minute."""
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
def login(data: UserLogin, request: Request, rate_lim=Depends(rate_limit(5, 60))):
    """Log in and retrieve access tokens or MFA challenges. Rate-limited to 5 requests per minute."""
    service = ServiceRegistry().auth_service
    res = service.login(
        username_or_email=data.username_or_email,
        password=data.password,
    )
    if isinstance(res, dict) and res.get("pending_mfa"):
        return res
    return {"access_token": res, "token_type": "bearer"}


@router.get("/verify-email")
def verify_email(token: str):
    """Verifies a user email verification token."""
    service = ServiceRegistry().user_service
    success = service.verify_email(token)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired email verification token.")
    return {"message": "Email verified successfully. You can now log in."}


@router.post("/forgot-password")
def forgot_password(data: ForgotPassword, request: Request, rate_lim=Depends(rate_limit(3, 60))):
    """Requests a password reset token. Rate-limited to 3 requests per minute."""
    service = ServiceRegistry().user_service
    # Returns 200 anyway to prevent user discovery scans
    service.request_password_reset(data.email_or_username)
    return {"message": "If the account exists, a password reset link has been sent to the registered email."}


@router.post("/reset-password")
def reset_password(data: ResetPassword):
    """Resets user password using reset token."""
    service = ServiceRegistry().user_service
    try:
        success = service.reset_password(data.token, data.new_password)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid or expired password reset token.")
        return {"message": "Password reset successfully. You can now log in."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/whoami")
def whoami(current_user=Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
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


# ── MFA Endpoints (Require Auth Sessions) ─────────────────────────────────────

@router.post("/mfa/setup")
def mfa_setup(current_user=Depends(get_current_user)):
    """Generates an MFA setup secret and provisioning URI."""
    service = ServiceRegistry().user_service
    return service.setup_mfa(current_user.username)


@router.post("/mfa/confirm")
def mfa_confirm(data: MFAConfirm, current_user=Depends(get_current_user)):
    """Confirms and enables MFA on user account, returning backup recovery codes."""
    service = ServiceRegistry().user_service
    backup_codes = service.confirm_mfa(current_user.username, data.secret, data.code)
    if backup_codes is None:
        raise HTTPException(status_code=400, detail="Invalid MFA verification code.")
    return {
        "mfa_enabled": True,
        "backup_codes": backup_codes,
        "message": "MFA has been successfully enabled. Please save your backup codes safely."
    }


@router.post("/mfa/disable")
def mfa_disable(data: MFADisable, current_user=Depends(get_current_user)):
    """Disables MFA on user account."""
    service = ServiceRegistry().user_service
    success = service.disable_mfa(current_user.username, data.code)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid verification code.")
    return {"message": "MFA has been successfully disabled."}


@router.post("/login/mfa")
def login_mfa(data: LoginMFA, request: Request, rate_lim=Depends(rate_limit(5, 60))):
    """Verifies MFA TOTP/backup code to finalize login session. Rate-limited to 5 requests per minute."""
    from conclave.server.security import decode_access_token, create_access_token
    payload = decode_access_token(data.mfa_token)
    if not payload or payload.get("type") != "mfa_challenge":
        raise HTTPException(status_code=400, detail="Invalid or expired MFA token.")
    
    username = payload.get("pending_mfa_user")
    service = ServiceRegistry().user_service
    
    if not service.login_mfa(username, data.code):
        service.audit_service.log_event(
            event_type="USER_MFA_LOGIN_FAILED",
            resource_type="User",
            resource_name=username,
            action="login_mfa",
            status="Failure",
            message="Invalid MFA code or backup code."
        )
        raise HTTPException(status_code=401, detail="Invalid MFA verification code or backup code.")
    
    user = service.get_user(username)
    final_token = create_access_token({
        "sub": user.username,
        "role": getattr(user, 'role', 'Operator'),
        "organization_id": user.organization_id,
    })
    
    service.audit_service.log_event(
        event_type="USER_LOGIN",
        resource_type="User",
        resource_name=user.username,
        action="login",
        status="Success",
        message=f"User '{user.username}' successfully authenticated via MFA."
    )
    return {"access_token": final_token, "token_type": "bearer"}
