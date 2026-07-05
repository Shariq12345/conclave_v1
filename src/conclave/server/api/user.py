from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission, get_current_user, verify_org_boundary

router = APIRouter(prefix="/users", tags=["Users"])


class UserCreate(BaseModel):
    username: str
    org_name: str
    email: str
    full_name: str
    role: Optional[str] = "Operator"


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None


@router.post("/create")
def create_user(data: UserCreate, current_user=Depends(require_permission("manage_users"))):
    registry = ServiceRegistry()
    # Enforce organization boundary: org admins can only create users in their own org
    org = registry.organization_service.get_organization(data.org_name)
    verify_org_boundary(org.id, current_user)
    user = registry.user_service.create_user(
        username=data.username,
        org_name=data.org_name,
        email=data.email,
        full_name=data.full_name,
        role=data.role or "Operator",
    )
    return user.to_dict()


@router.get("/list")
def list_users(current_user=Depends(require_permission("manage_users"))):
    service = ServiceRegistry().user_service
    users = service.list_users()
    # System Admin sees everyone; others see only their org
    if not current_user.is_system_admin:
        users = [u for u in users if u.organization_id == current_user.organization_id]
    return [u.to_dict() for u in users]


@router.get("/show/{username}")
def show_user(username: str, current_user=Depends(require_permission("manage_users"))):
    service = ServiceRegistry().user_service
    user = service.get_user(username)
    verify_org_boundary(user.organization_id, current_user)
    return user.to_dict()


@router.post("/update/{username}")
def update_user(username: str, data: UserUpdate, current_user=Depends(require_permission("manage_users"))):
    service = ServiceRegistry().user_service
    user = service.get_user(username)
    verify_org_boundary(user.organization_id, current_user)
    updated = service.update_user(username=username, email=data.email, full_name=data.full_name)
    return updated.to_dict()


@router.post("/deactivate/{username}")
def deactivate_user(username: str, current_user=Depends(require_permission("manage_users"))):
    service = ServiceRegistry().user_service
    user = service.get_user(username)
    verify_org_boundary(user.organization_id, current_user)
    updated = service.deactivate_user(username)
    return updated.to_dict()


@router.delete("/remove/{username}")
def remove_user(username: str, current_user=Depends(require_permission("manage_users"))):
    service = ServiceRegistry().user_service
    user = service.get_user(username)
    verify_org_boundary(user.organization_id, current_user)
    success = service.remove_user(username)
    return {"success": success}

