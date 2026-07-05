"""
conclave.server.api.onboarding
───────────────────────────────
Public + protected endpoints for the first-time setup wizard.

Public (no auth):
  GET  /onboarding/status          → { initialized, org_count }
  POST /onboarding/create          → Scenario 1: create org + admin user
  POST /onboarding/join            → Scenario 2: submit a join request

Protected (Org Admin — approve_joins permission):
  GET  /onboarding/pending         → list pending join requests for caller's org
  POST /onboarding/approve/{id}    → approve a join request
  POST /onboarding/reject/{id}     → reject a join request
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission, get_current_user

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


# ── Request schemas ───────────────────────────────────────────────────────────

class OnboardingCreateRequest(BaseModel):
    org_name: str
    org_type: str
    org_description: Optional[str] = ""
    username: str
    email: str
    full_name: str
    password: str


class JoinRequest(BaseModel):
    org_name: str          # organization name or ID to join
    username: str
    email: str
    full_name: str
    password: str


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/status")
def onboarding_status():
    """
    Returns whether this Conclave server has been initialized.
    Used by the CLI to decide whether to show the onboarding wizard.
    """
    svc = ServiceRegistry().onboarding_service
    return svc.get_status()


@router.post("/create")
def onboarding_create(data: OnboardingCreateRequest):
    """
    Scenario 1 — Create a new organization and its first administrator.
    Only callable when the server has zero organizations (not initialized).
    Returns the access token so the CLI can log in immediately.
    """
    svc = ServiceRegistry().onboarding_service
    org, user, token = svc.create_with_org(
        org_name=data.org_name,
        org_type=data.org_type,
        description=data.org_description or "",
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        password=data.password,
    )
    return {
        "organization": org.to_dict(),
        "user": user.to_dict(),
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/join")
def onboarding_join(data: JoinRequest):
    """
    Scenario 2 — Submit a join request for an existing organization.
    The invite code shown here should be shared with the Org Admin to identify the request.
    """
    svc = ServiceRegistry().onboarding_service
    req = svc.request_join(
        org_id=data.org_name,
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        password=data.password,
    )
    return {
        "join_request": req.to_dict(),
        "message": (
            f"Your join request has been submitted to the organization administrator. "
            f"Your invite code is: {req.invite_code}. "
            f"Once approved, you can log in using 'auth login'."
        ),
    }


# ── Protected endpoints (Org Admin only) ─────────────────────────────────────

@router.get("/pending")
def list_pending(current_user=Depends(require_permission("approve_joins"))):
    """List all pending join requests for the caller's organization."""
    svc = ServiceRegistry().onboarding_service
    requests = svc.list_pending_requests(current_user.organization_id)
    return [r.to_dict() for r in requests]


@router.post("/approve/{request_id}")
def approve_join(request_id: str, current_user=Depends(require_permission("approve_joins"))):
    """Approve a pending join request. The user becomes an Operator."""
    svc = ServiceRegistry().onboarding_service
    user = svc.approve_join(request_id=request_id, reviewed_by=current_user.username)
    return {
        "approved_user": user.to_dict(),
        "message": f"User '{user.username}' has been approved and can now log in.",
    }


@router.post("/reject/{request_id}")
def reject_join(request_id: str, current_user=Depends(require_permission("approve_joins"))):
    """Reject a pending join request."""
    svc = ServiceRegistry().onboarding_service
    req = svc.reject_join(request_id=request_id, reviewed_by=current_user.username)
    return {
        "join_request": req.to_dict(),
        "message": f"Join request for '{req.username}' has been rejected.",
    }
