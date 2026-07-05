from fastapi import APIRouter, Depends
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/list")
def list_logs(current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().audit_service
    events = service.get_all_events()
    return [e.to_dict() for e in events]


@router.get("/show/{event_id}")
def show_log(event_id: str, current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().audit_service
    event = service.get_event(event_id)
    return event.to_dict()


@router.post("/clear")
def clear_logs(current_user=Depends(require_permission("clear_audit"))):
    service = ServiceRegistry().audit_service
    service.clear_logs()
    return {"success": True}


@router.get("/verify")
def verify_ledger(current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().audit_service
    try:
        res = service.verify_ledger()
        return res
    except ValueError as e:
        return {"status": "Compromised", "error": str(e)}

