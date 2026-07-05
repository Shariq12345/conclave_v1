from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission, get_current_user, verify_org_boundary

router = APIRouter(prefix="/organizations", tags=["Organizations"])


class OrganizationCreate(BaseModel):
    name: str
    organization_type: str
    description: Optional[str] = ""


class OrganizationUpdate(BaseModel):
    organization_type: Optional[str] = None
    description: Optional[str] = None


@router.post("/create")
def create_organization(data: OrganizationCreate, current_user=Depends(require_permission("manage_organizations"))):
    service = ServiceRegistry().organization_service
    org = service.create_organization(
        name=data.name,
        organization_type=data.organization_type,
        description=data.description,
    )
    return org.to_dict()


@router.get("/list")
def list_organizations(current_user=Depends(require_permission("manage_organizations"))):
    service = ServiceRegistry().organization_service
    orgs = service.list_organizations()
    return [o.to_dict() for o in orgs]


@router.get("/show/{name}")
def show_organization(name: str, current_user=Depends(get_current_user)):
    service = ServiceRegistry().organization_service
    org = service.get_organization(name)
    # Non-admins can only view their own organization
    verify_org_boundary(org.id, current_user)
    return org.to_dict()


@router.post("/update/{name}")
def update_organization(name: str, data: OrganizationUpdate, current_user=Depends(require_permission("manage_organizations"))):
    service = ServiceRegistry().organization_service
    org = service.update_organization(
        name=name,
        organization_type=data.organization_type,
        description=data.description,
    )
    return org.to_dict()


@router.post("/deactivate/{name}")
def deactivate_organization(name: str, current_user=Depends(require_permission("manage_organizations"))):
    service = ServiceRegistry().organization_service
    org = service.deactivate_organization(name)
    return org.to_dict()


@router.delete("/remove/{name}")
def remove_organization(name: str, current_user=Depends(require_permission("manage_organizations"))):
    service = ServiceRegistry().organization_service
    success = service.remove_organization(name)
    return {"success": success}

