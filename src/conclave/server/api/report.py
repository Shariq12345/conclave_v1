from fastapi import APIRouter, Depends, HTTPException, Query, Response
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/generate")
def generate_report(
    type: str = Query(..., description="Report type (audit, training, organization, user_activity, node_inventory, governance_compliance, system_health)"),
    start_date: str = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str = Query(None, description="End date YYYY-MM-DD"),
    current_user = Depends(require_permission("view_audit"))
):
    registry = ServiceRegistry()
    org_id = current_user.organization_id if not current_user.is_system_admin else "all"
    
    try:
        report = registry.reporting_service.generate_report(
            report_type=type,
            generated_by=current_user.username,
            org_id=org_id,
            start_date=start_date,
            end_date=end_date
        )
        return report.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {e}")

@router.get("/export")
def export_report(
    type: str = Query(..., description="Report type"),
    format: str = Query(..., description="Export format (pdf, csv, json)"),
    start_date: str = Query(None),
    end_date: str = Query(None),
    current_user = Depends(require_permission("view_audit"))
):
    registry = ServiceRegistry()
    org_id = current_user.organization_id if not current_user.is_system_admin else "all"
    
    try:
        report = registry.reporting_service.generate_report(
            report_type=type,
            generated_by=current_user.username,
            org_id=org_id,
            start_date=start_date,
            end_date=end_date
        )
        
        export_bytes = registry.reporting_service.export_report(report, format)
        
        media_types = {
            "pdf": "application/pdf",
            "csv": "text/csv",
            "json": "application/json"
        }
        media_type = media_types.get(format.lower(), "application/octet-stream")
        
        filename = f"{type}_report.{format.lower()}"
        
        return Response(
            content=export_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export report: {e}")
