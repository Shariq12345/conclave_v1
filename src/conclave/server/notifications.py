import uuid
from datetime import datetime
from typing import List, Optional
from conclave.models import Notification

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
        print(f"[Slack Stub Webhook] Sent notification: {payload}")

class EmailNotificationChannel(NotificationChannel):
    def send(self, notification: Notification):
        print(f"[Email Stub] Sent email to {notification.recipient} with subject '{notification.title}': {notification.message}")

class WebSocketNotificationChannel(NotificationChannel):
    def send(self, notification: Notification):
        payload = {
            "event": "notification",
            "data": notification.to_dict()
        }
        print(f"[WebSocket Broadcast Stub] Broadcast payload: {payload}")

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
