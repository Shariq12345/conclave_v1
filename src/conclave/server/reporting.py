import io
import csv
import json
import uuid
from datetime import datetime
from typing import List, Optional
from conclave.models import Report

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

class ReportingService:
    def __init__(self, registry):
        self.registry = registry

    def generate_report(self, report_type: str, generated_by: str, org_id: str, start_date: str = None, end_date: str = None) -> Report:
        """
        Gathers system governance and metric records and compiles them into a structured report.
        """
        # Resolve user organization name
        org_name = "all"
        if org_id and org_id != "all":
            org = self.registry.organization_service.repository.find_by_name(org_id)
            if org:
                org_name = org.name
            else:
                for o in self.registry.organization_service.list_organizations():
                    if o.id == org_id or o.name == org_id:
                        org_name = o.name
                        break
                else:
                    org_name = org_id

        # Setup date filters
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
        date_range_str = f"{start_date or 'Beginning'} to {end_date or 'Present'}"

        def within_range(ts):
            if not ts:
                return True
            if isinstance(ts, str):
                try:
                    # ISO format parsing
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    return True
            if start_dt and ts.date() < start_dt.date():
                return False
            if end_dt and ts.date() > end_dt.date():
                return False
            return True

        title = f"{report_type.replace('_', ' ').title()} Report"
        summary = {}
        detailed_data = []

        # 1. Audit Report
        if report_type == "audit":
            events = self.registry.audit_service.get_all_events()
            filtered = [e for e in events if within_range(e.timestamp)]
            
            success_count = sum(1 for e in filtered if e.status.lower() == "success")
            total = len(filtered)
            summary = {
                "total_audit_events": total,
                "success_count": success_count,
                "failure_count": total - success_count,
                "success_rate_percentage": round((success_count / total * 100.0), 1) if total > 0 else 100.0,
                "critical_security_alerts": sum(1 for e in filtered if "violation" in e.event_type.lower() or e.event_type == "USER_LOGIN_FAILED")
            }
            detailed_data = [{
                "id": e.id[:8],
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "resource": f"{e.resource_type}: {e.resource_name}",
                "action": e.action,
                "status": e.status,
                "message": e.message
            } for e in filtered]

        # 2. Training Report
        elif report_type == "training":
            sessions = self.registry.training_service.list_sessions()
            filtered = [s for s in sessions if within_range(s.created_at)]
            
            status_counts = {}
            for s in filtered:
                status_counts[s.status] = status_counts.get(s.status, 0) + 1
                
            durations = []
            for s in filtered:
                if s.status == "Completed" and s.started_at and s.completed_at:
                    durations.append((s.completed_at - s.started_at).total_seconds())
            avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

            summary = {
                "total_training_sessions": len(filtered),
                "completed_sessions": status_counts.get("Completed", 0),
                "failed_sessions": status_counts.get("Failed", 0),
                "running_sessions": status_counts.get("Running", 0),
                "interrupted_sessions": status_counts.get("Interrupted", 0) or status_counts.get("Stopped", 0),
                "average_duration_seconds": avg_duration
            }
            detailed_data = [{
                "session_id": s.id[:8],
                "name": s.name,
                "status": s.status,
                "assigned_policy": s.assigned_policy,
                "dataset": s.dataset_name,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "priority": s.priority
            } for s in filtered]

        # 3. Organization Report
        elif report_type == "organization":
            orgs = self.registry.organization_service.list_organizations()
            nodes = self.registry.node_service.list_nodes()
            users = self.registry.user_service.list_users()

            summary = {
                "total_registered_organizations": len(orgs),
                "active_organizations": sum(1 for o in orgs if o.status == "Active"),
                "total_nodes_deployed": len(nodes),
                "total_registered_users": len(users)
            }
            
            detailed_data = []
            for o in orgs:
                org_node_count = sum(1 for n in nodes if n.organization_id == o.id)
                org_user_count = sum(1 for u in users if u.organization_id == o.id)
                detailed_data.append({
                    "org_id": o.id[:8],
                    "name": o.name,
                    "type": o.organization_type,
                    "status": o.status,
                    "created_at": o.created_at.isoformat() if o.created_at else "",
                    "node_count": org_node_count,
                    "user_count": org_user_count
                })

        # 4. User Activity Report
        elif report_type == "user_activity":
            users = self.registry.user_service.list_users()
            events = self.registry.audit_service.get_all_events()

            summary = {
                "total_users": len(users),
                "active_users": sum(1 for u in users if u.status == "Active"),
                "role_distribution": {
                    "System Admin": sum(1 for u in users if u.role == "System Admin"),
                    "Organization Admin": sum(1 for u in users if u.role == "Organization Admin"),
                    "Operator": sum(1 for u in users if u.role == "Operator"),
                    "Auditor": sum(1 for u in users if u.role == "Auditor")
                }
            }
            
            detailed_data = []
            for u in users:
                user_events = [e for e in events if e.resource_name == u.username]
                logins = sum(1 for e in user_events if e.event_type == "USER_LOGIN")
                failed_logins = sum(1 for e in user_events if e.event_type == "USER_LOGIN_FAILED")
                detailed_data.append({
                    "username": u.username,
                    "full_name": u.full_name,
                    "role": u.role,
                    "status": u.status,
                    "last_login": u.last_login.isoformat() if u.last_login else "Never",
                    "login_count": logins,
                    "failed_login_count": failed_logins
                })

        # 5. Node Inventory Report
        elif report_type == "node_inventory":
            nodes = self.registry.node_service.list_nodes()
            filtered = [n for n in nodes if within_range(n.registered_at)]

            summary = {
                "total_nodes": len(filtered),
                "online_nodes": sum(1 for n in filtered if n.status == "Online"),
                "offline_nodes": sum(1 for n in filtered if n.status == "Offline"),
                "approved_nodes": sum(1 for n in filtered if n.status == "Approved"),
                "total_cpu_cores": sum(n.cpu_cores for n in filtered),
                "total_ram_gb": round(sum(n.ram_gb for n in filtered), 1)
            }
            detailed_data = [{
                "node_id": n.id[:8],
                "hostname": n.hostname,
                "os": f"{n.os_name} {n.os_version}".strip(),
                "cores": n.cpu_cores,
                "ram_gb": round(n.ram_gb, 1),
                "gpu": n.gpu_available,
                "status": n.status,
                "trust_status": n.trust_status,
                "last_heartbeat": n.last_heartbeat.isoformat() if n.last_heartbeat else ""
            } for n in filtered]

        # 6. Governance Compliance Report
        elif report_type == "governance_compliance":
            policies = self.registry.policy_service.list_policies()
            consents = self.registry.consent_service.repository.find_all()
            events = self.registry.audit_service.get_all_events()

            violations = sum(1 for e in events if "policy_violation" in e.event_type.lower() or "violation" in e.event_type.lower())
            validation_failures = sum(1 for e in events if "orchestrator_validation" in e.event_type.lower() and e.status.lower() == "failure")

            summary = {
                "total_governance_policies": len(policies),
                "active_policies": sum(1 for p in policies if p.status == "Enabled"),
                "total_data_consents": len(consents),
                "active_consents": sum(1 for c in consents if c.status == "Granted"),
                "policy_violations_recorded": violations,
                "governance_check_failures": validation_failures
            }
            detailed_data = [{
                "id": p.id[:8],
                "policy_name": p.name,
                "status": p.status,
                "secagg": "Enabled" if p.secagg_enabled else "Disabled",
                "differential_privacy": "Enabled" if p.dp_enabled else "Disabled",
                "dp_epsilon": p.dp_epsilon,
                "dp_delta": p.dp_delta
            } for p in policies]

        # 7. System Health Report
        elif report_type == "system_health":
            nodes = self.registry.node_service.list_nodes()
            alerts = self.registry.monitoring_service.get_active_alerts()

            cpu_vals, ram_vals = [], []
            for n in nodes:
                if n.status == "Online":
                    metrics = self.registry.monitoring_service.get_latest_node_metrics(n.id)
                    if metrics:
                        cpu_vals.append(metrics["cpu"])
                        ram_vals.append(metrics["ram"])

            avg_cpu = round(sum(cpu_vals) / len(cpu_vals), 1) if cpu_vals else 0.0
            avg_ram = round(sum(ram_vals) / len(ram_vals), 1) if ram_vals else 0.0

            summary = {
                "active_alerts": len(alerts),
                "critical_alerts": sum(1 for a in alerts if a.get("severity") == "Critical"),
                "warning_alerts": sum(1 for a in alerts if a.get("severity") == "Warning"),
                "online_nodes": sum(1 for n in nodes if n.status == "Online"),
                "offline_nodes": sum(1 for n in nodes if n.status == "Offline"),
                "average_cpu_utilization_percent": avg_cpu,
                "average_ram_utilization_percent": avg_ram
            }
            detailed_data = [{
                "alert_id": a.get("id")[:8],
                "timestamp": a.get("timestamp"),
                "severity": a.get("severity"),
                "source": a.get("source"),
                "message": a.get("message")
            } for a in alerts]

        else:
            raise ValueError(f"Unknown report type '{report_type}'.")

        report = Report(
            title=title,
            generated_by=generated_by,
            organization=org_name,
            date_range=date_range_str,
            summary=summary,
            detailed_data=detailed_data,
            timestamp=datetime.now()
        )

        # Log report generation audit event
        self.registry.audit_service.log_event(
            event_type="REPORT_GENERATED",
            resource_type="Report",
            resource_name=report_type,
            action="generate",
            status="Success",
            message=f"Report '{report_type}' generated by '{generated_by}' covering '{date_range_str}'."
        )

        return report

    def export_report(self, report: Report, export_format: str) -> bytes:
        """
        Serializes the report data into the requested export format bytes.
        """
        fmt = export_format.lower().strip()
        
        # Log export audit event
        self.registry.audit_service.log_event(
            event_type="REPORT_EXPORTED",
            resource_type="Report",
            resource_name=report.title.replace(" Report", "").lower().strip(),
            action="export",
            status="Success",
            message=f"Report '{report.title}' exported as '{fmt}' format by '{report.generated_by}'."
        )

        if fmt == "json":
            return json.dumps(report.to_dict(), indent=4).encode('utf-8')

        elif fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Report Title", report.title])
            writer.writerow(["Generated By", report.generated_by])
            writer.writerow(["Organization", report.organization])
            writer.writerow(["Date Range", report.date_range])
            writer.writerow(["Timestamp", report.timestamp.isoformat()])
            writer.writerow([])
            
            writer.writerow(["--- Executive Summary ---"])
            for k, v in report.summary.items():
                writer.writerow([k.replace('_', ' ').title(), v])
            writer.writerow([])
            
            writer.writerow(["--- Detailed Data ---"])
            if report.detailed_data:
                keys = list(report.detailed_data[0].keys())
                writer.writerow([k.replace('_', ' ').title() for k in keys])
                for row in report.detailed_data:
                    writer.writerow([row.get(k, '') for k in keys])
            else:
                writer.writerow(["No detailed data available."])
                
            return output.getvalue().encode('utf-8')

        elif fmt == "pdf":
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=36,
                leftMargin=36,
                topMargin=36,
                bottomMargin=36
            )
            
            styles = getSampleStyleSheet()
            
            title_style = ParagraphStyle(
                'ReportTitle',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=20,
                leading=24,
                textColor=colors.HexColor("#1e293b"),
                spaceAfter=15
            )
            
            section_style = ParagraphStyle(
                'ReportSection',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=12,
                leading=16,
                textColor=colors.HexColor("#3b82f6"),
                spaceBefore=15,
                spaceAfter=8
            )
            
            normal_style = ParagraphStyle(
                'ReportNormal',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=9,
                leading=13,
                textColor=colors.HexColor("#334155")
            )
            
            th_style = ParagraphStyle(
                'TableHead',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8,
                leading=10,
                textColor=colors.white
            )
            
            td_style = ParagraphStyle(
                'TableCell',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=8,
                leading=10,
                textColor=colors.HexColor("#334155")
            )

            story = []
            
            story.append(Paragraph(report.title, title_style))
            story.append(Spacer(1, 8))
            
            meta_data = [
                [Paragraph("<b>Generated By:</b>", normal_style), Paragraph(report.generated_by, normal_style),
                 Paragraph("<b>Organization:</b>", normal_style), Paragraph(report.organization, normal_style)],
                [Paragraph("<b>Date Range:</b>", normal_style), Paragraph(report.date_range, normal_style),
                 Paragraph("<b>Timestamp:</b>", normal_style), Paragraph(report.timestamp.strftime("%Y-%m-%d %H:%M:%S"), normal_style)]
            ]
            meta_table = Table(meta_data, colWidths=[1.2*inch, 2.2*inch, 1.2*inch, 2.2*inch])
            meta_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('LINEBELOW', (0,-1), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ]))
            story.append(meta_table)
            story.append(Spacer(1, 15))
            
            story.append(Paragraph("Executive Summary", section_style))
            summary_data = []
            for k, v in report.summary.items():
                val_str = str(v)
                if isinstance(v, dict):
                    val_str = ", ".join(f"{dk}: {dv}" for dk, dv in v.items())
                summary_data.append([
                    Paragraph(f"<b>{k.replace('_', ' ').title()}:</b>", normal_style),
                    Paragraph(val_str, normal_style)
                ])
            
            summary_table = Table(summary_data, colWidths=[2.5*inch, 4.7*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('LEFTPADDING', (0,0), (-1,-1), 10),
                ('RIGHTPADDING', (0,0), (-1,-1), 10),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 15))
            
            story.append(Paragraph("Detailed Data", section_style))
            if not report.detailed_data:
                story.append(Paragraph("No detailed data records found.", normal_style))
            else:
                sample = report.detailed_data[0]
                keys = list(sample.keys())
                headers = [k.replace('_', ' ').title() for k in keys]
                
                table_content = [[Paragraph(h, th_style) for h in headers]]
                for row in report.detailed_data:
                    table_content.append([Paragraph(str(row.get(k, '')), td_style) for k in keys])
                    
                num_cols = len(headers)
                avail_width = 7.4 * inch
                col_widths = [avail_width / num_cols] * num_cols
                
                detail_table = Table(table_content, colWidths=col_widths, repeatRows=1)
                
                t_style = [
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1e293b")),
                    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('TOPPADDING', (0,0), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
                ]
                for idx in range(1, len(table_content)):
                    bg = colors.white if idx % 2 == 1 else colors.HexColor("#f1f5f9")
                    t_style.append(('BACKGROUND', (0, idx), (-1, idx), bg))
                    
                detail_table.setStyle(TableStyle(t_style))
                story.append(detail_table)
                
            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes

        else:
            raise ValueError(f"Unsupported export format '{export_format}'. Supported formats: pdf, csv, json.")
