from fastapi import APIRouter, Depends
from pydantic import BaseModel
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission, verify_org_boundary

router = APIRouter(prefix="/consents", tags=["Consents"])


class ConsentRequest(BaseModel):
    client_name: str
    dataset_name: str


@router.post("/grant")
def grant_consent(data: ConsentRequest, current_user=Depends(require_permission("manage_consents"))):
    registry = ServiceRegistry()
    # Verify the client belongs to the caller's org
    client = registry.client_service.get_client(data.client_name)
    verify_org_boundary(getattr(client, 'organization_id', current_user.organization_id), current_user)
    consent = registry.consent_service.grant_consent(data.client_name, data.dataset_name)
    return consent.to_dict()


@router.post("/revoke")
def revoke_consent(data: ConsentRequest, current_user=Depends(require_permission("manage_consents"))):
    registry = ServiceRegistry()
    client = registry.client_service.get_client(data.client_name)
    verify_org_boundary(getattr(client, 'organization_id', current_user.organization_id), current_user)
    consent = registry.consent_service.revoke_consent(data.client_name, data.dataset_name)
    return consent.to_dict()


@router.get("/list")
def list_consents(current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().consent_service
    consents = service.list_consents()
    return [c.to_dict() for c in consents]


@router.get("/show/{client_name}")
def show_consent_for_client(client_name: str, current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().consent_service
    consents = service.get_consents_for_client(client_name)
    return [c.to_dict() for c in consents]

