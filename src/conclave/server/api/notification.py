from fastapi import APIRouter, Depends, HTTPException
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("/list")
def list_notifications(current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().notification_service
    notifications = service.get_notifications()
    
    if not current_user.is_system_admin:
        try:
            org = ServiceRegistry().organization_service.get_organization(current_user.organization_id)
            org_name = org.name
        except Exception:
            org_name = current_user.organization_id
            
        filtered = []
        for n in notifications:
            if n.organization in ("all", "", org_name) or n.organization == current_user.organization_id:
                filtered.append(n)
        notifications = filtered
        
    return [n.to_dict() for n in notifications]

@router.post("/read/{notification_id}")
def mark_as_read(notification_id: str, current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().notification_service
    
    # Resolve prefix to full ID
    found = None
    for n in service.get_notifications():
        if n.id == notification_id or n.id.startswith(notification_id):
            found = n
            break
            
    if not found:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found.")
        
    if not current_user.is_system_admin:
        try:
            org = ServiceRegistry().organization_service.get_organization(current_user.organization_id)
            org_name = org.name
        except Exception:
            org_name = current_user.organization_id
            
        if found.organization not in ("all", "", org_name) and found.organization != current_user.organization_id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot modify notifications belonging to another organization.")

    success = service.mark_as_read(found.id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found.")
    return {"success": True}

@router.post("/read-all")
def mark_all_read(current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().notification_service
    if not current_user.is_system_admin:
        try:
            org = ServiceRegistry().organization_service.get_organization(current_user.organization_id)
            org_name = org.name
        except Exception:
            org_name = current_user.organization_id
            
        count = 0
        for n in service.get_unread_notifications():
            if n.organization in ("all", "", org_name) or n.organization == current_user.organization_id:
                if service.mark_as_read(n.id):
                    count += 1
        return {"success": True, "count": count}
        
    count = service.mark_all_read()
    return {"success": True, "count": count}
