from fastapi import APIRouter, Depends, HTTPException
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission

router = APIRouter(prefix="/monitor", tags=["Monitor"])

@router.get("/status")
def get_monitoring_status(current_user=Depends(require_permission("view_audit"))):
    """
    Get consolidated monitoring status including node states, session progress, and active alerts.
    """
    service = ServiceRegistry().monitoring_service
    return service.get_status_summary()

@router.post("/alert/resolve/{alert_id}")
def resolve_alert(alert_id: str, current_user=Depends(require_permission("manage_policies"))):
    """
    Mark an active alert as resolved.
    """
    service = ServiceRegistry().monitoring_service
    success = service.resolve_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert with ID '{alert_id}' not found or already resolved.")
    return {"success": True}
