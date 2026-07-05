"""
conclave.server.api.node
────────────────────────
REST API endpoints for node management.
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission, get_current_user, verify_org_boundary

router = APIRouter(prefix="/nodes", tags=["Nodes"])


# ── Request schemas ───────────────────────────────────────────────────────────

class NodeRegister(BaseModel):
    organization_id: Optional[str] = None
    hostname: str
    node_name: Optional[str] = None
    os_name: Optional[str] = ""
    os_version: Optional[str] = ""
    architecture: Optional[str] = ""
    cpu_model: Optional[str] = ""
    cpu_cores: Optional[int] = 0
    ram_gb: Optional[float] = 0.0
    gpu_available: Optional[str] = "No"
    gpu_vendor: Optional[str] = ""
    gpu_model: Optional[str] = ""
    gpu_count: Optional[int] = 0
    gpu_vram: Optional[float] = 0.0
    cuda_version: Optional[str] = ""
    python_version: Optional[str] = ""
    flower_version: Optional[str] = ""
    conclave_version: Optional[str] = ""
    public_key: str


# ── REST API Router endpoints ──────────────────────────────────────────────────

@router.post("/register")
def register_node(data: NodeRegister, request: Request, current_user=Depends(require_permission("register_nodes"))):
    """
    Register a new node (machine). Automatically sets organization to current user's
    organization unless specified otherwise (only allowed for System Admin).
    """
    registry = ServiceRegistry()
    org_id = data.organization_id or current_user.organization_id

    # Enforce boundary: Org admin and operators can only register nodes in their own org
    verify_org_boundary(org_id, current_user)

    client_ip = request.client.host if request.client else "127.0.0.1"

    node = registry.node_service.register_node(
        organization_id=org_id,
        hostname=data.hostname,
        public_key=data.public_key,
        node_name=data.node_name,
        os_name=data.os_name,
        os_version=data.os_version,
        architecture=data.architecture,
        cpu_model=data.cpu_model,
        cpu_cores=data.cpu_cores,
        ram_gb=data.ram_gb,
        gpu_available=data.gpu_available,
        gpu_vendor=data.gpu_vendor,
        gpu_model=data.gpu_model,
        gpu_count=data.gpu_count,
        gpu_vram=data.gpu_vram,
        cuda_version=data.cuda_version,
        python_version=data.python_version,
        flower_version=data.flower_version,
        conclave_version=data.conclave_version,
        last_ip=client_ip
    )
    return node.to_dict()


def verify_node_token(node_id: str, request: Request):
    """
    Decodes the JWT in X-Node-Token header using the node's registered public key.
    Raises HTTP 401 if invalid.
    """
    token = request.headers.get("X-Node-Token")
    if not token:
        raise HTTPException(status_code=401, detail="X-Node-Token header missing.")

    registry = ServiceRegistry()
    node = registry.node_service.node_repository.find_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    if not node.public_key:
        raise HTTPException(status_code=400, detail="Node public key not registered on server.")

    import jwt
    try:
        payload = jwt.decode(token, node.public_key, algorithms=["RS256"])
    except Exception as e:
        # Log auth failure event
        registry.audit_service.log_event(
            event_type="NODE_AUTH_FAILED",
            resource_type="Node",
            resource_name=node.hostname,
            action="heartbeat_auth",
            status="Failure",
            message=f"Node cryptographic verification failed: {e}"
        )
        raise HTTPException(status_code=401, detail=f"Cryptographic node validation failed: {e}")

    if payload.get("sub") != node_id:
        raise HTTPException(status_code=401, detail="Token subject mismatch.")
    return True


@router.get("/list")
def list_nodes(current_user=Depends(require_permission("view_nodes"))):
    """
    List all registered nodes. System Admins see all nodes.
    Other roles see only nodes belonging to their organization.
    """
    svc = ServiceRegistry().node_service
    if current_user.is_system_admin:
        nodes = svc.list_nodes()
    else:
        nodes = svc.list_nodes(current_user.organization_id)
    return [n.to_dict() for n in nodes]


@router.get("/show/{node_id}")
def show_node(node_id: str, current_user=Depends(require_permission("view_nodes"))):
    """View details of a specific node."""
    svc = ServiceRegistry().node_service
    node = svc.get_node(node_id)
    verify_org_boundary(node.organization_id, current_user)
    return node.to_dict()


@router.post("/approve/{node_id}")
def approve_node(node_id: str, current_user=Depends(require_permission("manage_nodes"))):
    """Approve a pending node to participate in Federated Learning."""
    svc = ServiceRegistry().node_service
    node = svc.get_node(node_id)
    verify_org_boundary(node.organization_id, current_user)
    approved = svc.approve_node(node_id, current_user.username)
    return approved.to_dict()


@router.post("/reject/{node_id}")
def reject_node(node_id: str, current_user=Depends(require_permission("manage_nodes"))):
    """Reject a pending node."""
    svc = ServiceRegistry().node_service
    node = svc.get_node(node_id)
    verify_org_boundary(node.organization_id, current_user)
    rejected = svc.reject_node(node_id, current_user.username)
    return rejected.to_dict()


@router.post("/revoke/{node_id}")
def revoke_node(node_id: str, current_user=Depends(require_permission("manage_nodes"))):
    """Revoke approval from a node. Revoked nodes cannot participate or send heartbeats."""
    svc = ServiceRegistry().node_service
    node = svc.get_node(node_id)
    verify_org_boundary(node.organization_id, current_user)
    revoked = svc.revoke_node(node_id, current_user.username)
    return revoked.to_dict()


@router.post("/heartbeat/{node_id}")
async def node_heartbeat(node_id: str, request: Request):
    """
    Report periodic node heartbeat. Supports dual authentication:
      1. Node Cryptographic Signature (via X-Node-Token header)
      2. User Bearer Auth (via Authorization header, requires register_nodes permission)
    """
    registry = ServiceRegistry()
    
    # If mTLS client certificate is presented, verify it matches node_id
    peercert = None
    transport = request.scope.get("transport")
    if transport:
        ssl_obj = transport.get_extra_info("ssl_object")
        if ssl_obj:
            peercert = ssl_obj.getpeercert()

    if peercert:
        cn = None
        for rdns in peercert.get("subject", []):
            for rdn in rdns:
                if rdn[0] == "commonName":
                    cn = rdn[1]
                    break
        if cn and cn != f"node-{node_id}":
            raise HTTPException(status_code=403, detail="Forbidden: Client certificate CN does not match node ID.")

    token = request.headers.get("X-Node-Token")
    client_ip = request.client.host if request.client else "127.0.0.1"

    if token:
        verify_node_token(node_id, request)
    else:
        # Fallback to user auth
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Authentication required. Provide X-Node-Token or Bearer User Token.")
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Malformed Authorization header.")

        from fastapi.security import HTTPAuthorizationCredentials
        from conclave.server.authz import get_current_user
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=parts[1])
        current_user = get_current_user(creds)

        if not current_user.has_permission("register_nodes"):
            raise HTTPException(status_code=403, detail="Forbidden: User lacks register_nodes permission.")

        node = registry.node_service.get_node(node_id)
        verify_org_boundary(node.organization_id, current_user)

    # Parse optional utilization metrics from request body
    body_data = {}
    try:
        body_data = await request.json()
    except Exception:
        pass

    cpu = body_data.get("cpu_utilization", 0.0)
    ram = body_data.get("ram_utilization", 0.0)
    gpu = body_data.get("gpu_utilization", 0.0)
    gpu_vram = body_data.get("gpu_vram_utilization", 0.0)
    gpu_temp = body_data.get("gpu_temp", 0.0)

    try:
        updated = registry.node_service.heartbeat(node_id, client_ip)
        resp = updated.to_dict()
        
        # Retrieve active task if any
        task = registry.training_service.orchestrator.get_active_task(node_id)
        status = "Online"
        if task:
            resp["active_task"] = task
            status = "Busy"
        else:
            status = "Idle"

        # Record metrics in the separate metrics database
        registry.monitoring_service.log_node_metrics(node_id, cpu, ram, gpu, gpu_vram, gpu_temp, status)

        return resp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
