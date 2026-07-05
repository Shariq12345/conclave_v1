from fastapi import APIRouter, Depends
from pydantic import BaseModel
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission, get_current_user

router = APIRouter(prefix="/clients", tags=["Clients"])


class ClientRegister(BaseModel):
    name: str


@router.post("/register")
def register_client(data: ClientRegister, current_user=Depends(require_permission("manage_clients"))):
    service = ServiceRegistry().client_service
    client = service.register_client(data.name)
    return client.to_dict()


@router.get("/list")
def list_clients(current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().client_service
    clients = service.list_clients()
    return [c.to_dict() for c in clients]


@router.get("/show/{name}")
def show_client(name: str, current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().client_service
    client = service.get_client(name)
    return client.to_dict()


@router.delete("/remove/{name}")
def remove_client(name: str, current_user=Depends(require_permission("manage_clients"))):
    service = ServiceRegistry().client_service
    success = service.remove_client(name)
    return {"success": success}
