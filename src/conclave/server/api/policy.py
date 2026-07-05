from fastapi import APIRouter, Depends
from pydantic import BaseModel
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission

router = APIRouter(prefix="/policies", tags=["Policies"])


class PolicyCreate(BaseModel):
    name: str
    description: str = ""
    secagg_enabled: bool = False
    dp_enabled: bool = False
    dp_epsilon: float = 1.0
    dp_delta: float = 1e-5


@router.post("/create")
def create_policy(data: PolicyCreate, current_user=Depends(require_permission("manage_policies"))):
    service = ServiceRegistry().policy_service
    policy = service.create_policy(
        name=data.name,
        description=data.description,
        secagg_enabled=data.secagg_enabled,
        dp_enabled=data.dp_enabled,
        dp_epsilon=data.dp_epsilon,
        dp_delta=data.dp_delta
    )
    return policy.to_dict()


@router.get("/list")
def list_policies(current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().policy_service
    policies = service.list_policies()
    return [p.to_dict() for p in policies]


@router.get("/show/{name}")
def show_policy(name: str, current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().policy_service
    policy = service.get_policy(name)
    return policy.to_dict()


@router.post("/enable/{name}")
def enable_policy(name: str, current_user=Depends(require_permission("manage_policies"))):
    service = ServiceRegistry().policy_service
    policy = service.enable_policy(name)
    return policy.to_dict()


@router.post("/disable/{name}")
def disable_policy(name: str, current_user=Depends(require_permission("manage_policies"))):
    service = ServiceRegistry().policy_service
    policy = service.disable_policy(name)
    return policy.to_dict()


@router.delete("/remove/{name}")
def remove_policy(name: str, current_user=Depends(require_permission("manage_policies"))):
    service = ServiceRegistry().policy_service
    success = service.remove_policy(name)
    return {"success": success}

