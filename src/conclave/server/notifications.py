import uuid
from datetime import datetime
from typing import List, Optional
import os
import requests
import asyncio
from fastapi import WebSocket
from conclave.models import Notification

# ── WebSocket Connection Manager ──────────────────────────────────────────────

class WebSocketConnectionManager:
    """Tracks and broadcasts JSON payloads to active WebSocket subscriber connections."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # iterate on a copy of connections list to prevent concurrency errors
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                if connection in self.active_connections:
                    self.active_connections.remove(connection)

ws_manager = WebSocketConnectionManager()


# ── Notification Channels ─────────────────────────────────────────────────────

class NotificationChannel:
    def send(self, notification: Notification):
        raise NotImplementedError

class DatabaseNotificationChannel(NotificationChannel):
    def __init__(self, repository):
        self.repository = repository

    def send(self, notification: Notification):
        self.repository.save(notification)

class SlackNotificationChannel(NotificationChannel):
    def send(self, notification: Notification):
        payload = {
            "text": f"*{notification.title}* ({notification.severity})\n{notification.message}"
        }
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if webhook_url:
            try:
                response = requests.post(webhook_url, json=payload, timeout=5)
                if response.status_code != 200:
                    print(f"[Slack Alert Error] Status {response.status_code}: {response.text}")
            except Exception as e:
                print(f"[Slack Alert Exception] Webhook post failed: {e}")
        else:
            print(f"[Slack Stub Webhook] Sent notification: {payload}")

class EmailNotificationChannel(NotificationChannel):
    def send(self, notification: Notification):
        to_email = notification.recipient
        # If recipient is "all" or non-email, try ADMIN_EMAIL or find the first active Org Admin
        if not to_email or to_email == "all" or "@" not in to_email:
            to_email = os.getenv("ADMIN_EMAIL")
            if not to_email:
                try:
                    from conclave.server.registry import ServiceRegistry
                    users = ServiceRegistry().user_service.list_users()
                    admins = [u.email for u in users if u.role == "Organization Admin" and u.email]
                    if admins:
                        to_email = admins[0]
                except Exception:
                    pass

        # If we resolve a valid email address, send it via Resend client
        if to_email and "@" in to_email:
            from conclave.server.security import send_resend_email
            subject = f"[Conclave Alert] {notification.title}"
            html_content = f"""
            <h3>Conclave System Notification</h3>
            <p><strong>Type:</strong> {notification.type}</p>
            <p><strong>Severity:</strong> {notification.severity}</p>
            <p><strong>Message:</strong> {notification.message}</p>
            <p><small>Timestamp: {notification.timestamp.isoformat()}</small></p>
            """
            success = send_resend_email(to_email, subject, html_content)
            if not success:
                print(f"[Email Send Failed] Could not deliver notification email to {to_email}")
        else:
            print(f"[Email Stub] Sent email to {notification.recipient} with subject '{notification.title}': {notification.message}")

class WebSocketNotificationChannel(NotificationChannel):
    def send(self, notification: Notification):
        payload = {
            "event": "notification",
            "data": notification.to_dict()
        }
        # Safely run async broadcast from synchronous handlers or helper threads
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(ws_manager.broadcast(payload))
        except RuntimeError:
            # Fallback if no loop is currently running on the execution thread
            asyncio.run(ws_manager.broadcast(payload))

class NotificationHub:
    def __init__(self):
        self.channels = []

    def register_channel(self, channel: NotificationChannel):
        self.channels.append(channel)

    def trigger_event(self, event_type: str, resource_name: str, status: str, message: str, recipient: str = "all", organization: str = "all", meta: dict = None):
        mapped = self.map_event(event_type, status, message, resource_name)
        if not mapped:
            return
            
        notifications_to_send = mapped if isinstance(mapped, list) else [mapped]
        
        for n_info in notifications_to_send:
            notification = Notification(
                type=n_info["type"],
                severity=n_info["severity"],
                title=n_info["title"],
                message=n_info["message"],
                recipient=recipient,
                organization=organization,
                timestamp=datetime.now(),
                read=False
            )
            for channel in self.channels:
                try:
                    channel.send(notification)
                except Exception as e:
                    print(f"Error sending notification via channel {channel}: {e}")

    def map_event(self, event_type: str, status: str, message: str, resource_name: str) -> Optional[List[dict] | dict]:
        evt = event_type.upper().strip()
        status = status.upper().strip()
        
        # 1. Training Started
        if evt in ("ORCHESTRATOR_START", "TRAINING_START", "TRAINING_STARTED"):
            return {
                "type": "Training Started",
                "severity": "Info",
                "title": f"Training Started: {resource_name}",
                "message": message
            }
        # 2. Training Completed
        elif evt in ("TRAINING_COMPLETED", "TRAINING_SUCCESS"):
            return {
                "type": "Training Completed",
                "severity": "Info",
                "title": f"Training Completed: {resource_name}",
                "message": message
            }
        # 3. Training Failed
        elif evt in ("TRAINING_FAILED", "TRAINING_FAILURE", "TRAINING_INTERRUPTED"):
            return {
                "type": "Training Failed",
                "severity": "Critical",
                "title": f"Training Failed: {resource_name}",
                "message": message
            }
        # 4/5. Node Registration & Approval Required
        elif evt in ("NODE_REGISTRATION", "NODE_REGISTERED"):
            return [
                {
                    "type": "Node Registered",
                    "severity": "Info",
                    "title": f"Node Registered: {resource_name}",
                    "message": message
                },
                {
                    "type": "Node Approval Required",
                    "severity": "Warning",
                    "title": f"Node Approval Required: {resource_name}",
                    "message": f"Node '{resource_name}' has registered and requires administrator approval."
                }
            ]
        # 6. Node Offline
        elif evt in ("NODE_OFFLINE", "NODE_DROPPED_OFFLINE"):
            return {
                "type": "Node Offline",
                "severity": "Critical",
                "title": f"Node Offline: {resource_name}",
                "message": message
            }
        # 7. Node Revoked
        elif evt in ("NODE_REVOCATION", "NODE_REVOKED"):
            return {
                "type": "Node Revoked",
                "severity": "Warning",
                "title": f"Node Revoked: {resource_name}",
                "message": message
            }
        # 8. User Created
        elif evt in ("USER_CREATION", "USER_CREATED") and status == "SUCCESS":
            return {
                "type": "User Created",
                "severity": "Info",
                "title": f"User Created: {resource_name}",
                "message": message
            }
        # 9. Organization Created
        elif evt in ("ORGANIZATION_CREATION", "ORGANIZATION_CREATED") and status == "SUCCESS":
            return {
                "type": "Organization Created",
                "severity": "Info",
                "title": f"Organization Created: {resource_name}",
                "message": message
            }
        # 10. Authentication Failures
        elif evt in ("USER_LOGIN_FAILED", "AUTHENTICATION_FAILURES", "AUTHENTICATION_FAILURE"):
            return {
                "type": "Authentication Failures",
                "severity": "Warning",
                "title": "Authentication Failure",
                "message": message
            }
        # 11. Governance Validation Failures
        elif evt in ("ORCHESTRATOR_VALIDATION", "GOVERNANCE_VALIDATION_FAILURES", "GOVERNANCE_VALIDATION_FAILURE") and status == "FAILURE":
            return {
                "type": "Governance Validation Failures",
                "severity": "Warning",
                "title": f"Governance Validation Failure: {resource_name}",
                "message": message
            }
        # 12. Policy Violations
        elif evt in ("POLICY_VIOLATION", "POLICY_VIOLATIONS") or ("VIOLATION" in evt):
            return {
                "type": "Policy Violations",
                "severity": "Critical",
                "title": f"Policy Violation: {resource_name}",
                "message": message
            }
        
        # Direct string prefix/containment mappings for name matches (case insensitive check)
        direct_types = {
            "TRAINING STARTED": ("Training Started", "Info", "Training Started"),
            "TRAINING COMPLETED": ("Training Completed", "Info", "Training Completed"),
            "TRAINING FAILED": ("Training Failed", "Critical", "Training Failed"),
            "NODE REGISTERED": ("Node Registered", "Info", "Node Registered"),
            "NODE APPROVAL REQUIRED": ("Node Approval Required", "Warning", "Node Approval Required"),
            "NODE OFFLINE": ("Node Offline", "Critical", "Node Offline"),
            "NODE REVOKED": ("Node Revoked", "Warning", "Node Revoked"),
            "USER CREATED": ("User Created", "Info", "User Created"),
            "ORGANIZATION CREATED": ("Organization Created", "Info", "Organization Created"),
            "AUTHENTICATION FAILURES": ("Authentication Failures", "Warning", "Authentication Failure"),
            "GOVERNANCE VALIDATION FAILURES": ("Governance Validation Failures", "Warning", "Governance Validation Failure"),
            "POLICY VIOLATIONS": ("Policy Violations", "Critical", "Policy Violation")
        }
        
        for key, val in direct_types.items():
            if key in evt.replace("_", " "):
                return {
                    "type": val[0],
                    "severity": val[1],
                    "title": f"{val[2]}: {resource_name}" if resource_name else val[2],
                    "message": message
                }
                
        return None
