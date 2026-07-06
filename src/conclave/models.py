import uuid
from datetime import datetime

class Client:
    def __init__(self, name: str, client_id: str = None, status: str = "Active", registered_at: datetime = None):
        self.id = client_id or str(uuid.uuid4())
        self.name = name.strip()
        self.status = status
        self.registered_at = registered_at or datetime.now()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "registered_at": self.registered_at.isoformat()
        }

class Policy:
    def __init__(self, name: str, description: str = "", policy_id: str = None, status: str = "Enabled", created_at: datetime = None, secagg_enabled: bool = False, dp_enabled: bool = False, dp_epsilon: float = 1.0, dp_delta: float = 1e-5):
        self.id = policy_id or str(uuid.uuid4())
        self.name = name.strip()
        self.description = description.strip()
        self.status = status  # "Enabled" or "Disabled"
        self.created_at = created_at or datetime.now()
        self.secagg_enabled = secagg_enabled
        self.dp_enabled = dp_enabled
        self.dp_epsilon = dp_epsilon
        self.dp_delta = dp_delta

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "secagg_enabled": self.secagg_enabled,
            "dp_enabled": self.dp_enabled,
            "dp_epsilon": self.dp_epsilon,
            "dp_delta": self.dp_delta
        }

class AuditEvent:
    def __init__(self, event_type: str, resource_type: str, resource_name: str, action: str, status: str, message: str, event_id: str = None, timestamp: datetime = None, hash: str = None, previous_hash: str = None):
        self.id = event_id or str(uuid.uuid4())
        self.timestamp = timestamp or datetime.now()
        self.event_type = event_type
        self.resource_type = resource_type.strip()
        self.resource_name = resource_name.strip()
        self.action = action.strip()
        self.status = status.strip()  # "Success" or "Failure"
        self.message = message.strip()
        self.hash = hash
        self.previous_hash = previous_hash

    def calculate_hash(self, prev_hash: str = None) -> str:
        import hashlib
        ph = prev_hash or self.previous_hash or "0"
        ts_str = self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp)
        payload = f"{ts_str}_{self.event_type}_{self.resource_type}_{self.resource_name}_{self.action}_{self.status}_{self.message}_{ph}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "resource_type": self.resource_type,
            "resource_name": self.resource_name,
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "hash": self.hash,
            "previous_hash": self.previous_hash
        }

class Consent:
    def __init__(self, client_id: str, dataset_name: str, status: str = "Granted", consent_id: str = None, granted_at: datetime = None, revoked_at: datetime = None):
        self.id = consent_id or str(uuid.uuid4())
        self.client_id = client_id
        self.dataset_name = dataset_name.strip()
        self.status = status  # "Granted" or "Revoked"
        self.granted_at = granted_at or datetime.now()
        self.revoked_at = revoked_at

    def to_dict(self):
        return {
            "id": self.id,
            "client_id": self.client_id,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "granted_at": self.granted_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None
        }


class TrainingSession:
    def __init__(self, name: str, participating_clients: list, assigned_policy: str, dataset_name: str, description: str = "", status: str = "Created", session_id: str = None, created_at: datetime = None, started_at: datetime = None, completed_at: datetime = None, priority: str = "Medium"):
        self.id = session_id or str(uuid.uuid4())
        self.name = name.strip()
        self.description = description.strip()
        self.participating_clients = [c.strip() for c in participating_clients]
        self.assigned_policy = assigned_policy.strip()
        self.dataset_name = dataset_name.strip()
        self.status = status  # "Created", "Running", "Completed", "Failed", "Stopped"
        self.created_at = created_at or datetime.now()
        self.started_at = started_at
        self.completed_at = completed_at
        self.priority = priority # "Low", "Medium", "High"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "participating_clients": self.participating_clients,
            "assigned_policy": self.assigned_policy,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "priority": self.priority
        }


class ValidationCheck:
    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name.strip()
        self.passed = passed
        self.message = message.strip()

    def to_dict(self):
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message
        }


class GovernanceValidationResult:
    def __init__(self, passed: bool, checks: list, timestamp: datetime = None):
        self.passed = passed
        self.checks = checks
        self.timestamp = timestamp or datetime.now()

    def to_dict(self):
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "timestamp": self.timestamp.isoformat()
        }


class Organization:
    def __init__(self, name: str, organization_type: str, description: str = "", status: str = "Active", org_id: str = None, created_at: datetime = None, updated_at: datetime = None):
        import uuid
        self.id = org_id or str(uuid.uuid4())
        self.name = name.strip()
        self.description = description.strip()
        self.organization_type = organization_type.strip()
        self.status = status
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "organization_type": self.organization_type,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class User:
    def __init__(self, username: str, email: str, full_name: str, organization_id: str = None, status: str = "Active", user_id: str = None, role: str = "Unassigned", password_hash: str = None, last_login: datetime = None, created_at: datetime = None, updated_at: datetime = None,
                 email_verified: bool = False, email_verification_token: str = None,
                 password_reset_token: str = None, password_reset_expires: datetime = None,
                 mfa_enabled: bool = False, mfa_secret: str = None, mfa_backup_codes: str = None):
        import uuid
        self.id = user_id or str(uuid.uuid4())
        self.organization_id = organization_id.strip() if organization_id else None
        self.username = username.strip()
        self.email = email.strip()
        self.full_name = full_name.strip()
        self.status = status
        self.role = role
        self.password_hash = password_hash
        self.last_login = last_login
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

        self.email_verified = email_verified
        self.email_verification_token = email_verification_token
        self.password_reset_token = password_reset_token
        self.password_reset_expires = password_reset_expires
        self.mfa_enabled = mfa_enabled
        self.mfa_secret = mfa_secret
        self.mfa_backup_codes = mfa_backup_codes

    def to_dict(self):
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "status": self.status,
            "role": self.role,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "email_verified": self.email_verified,
            "mfa_enabled": self.mfa_enabled
        }
class JoinRequest:
    """
    Represents a pending request from a user who wants to join an existing organization.
    Created during onboarding Scenario 2. The Org Admin reviews and approves/rejects.
    """
    def __init__(self, org_id: str, username: str, email: str, full_name: str,
                 password_hash: str, invite_code: str = None,
                 status: str = "Pending", request_id: str = None,
                 reviewed_by: str = None, reviewed_at: datetime = None,
                 created_at: datetime = None):
        import uuid
        self.id = request_id or str(uuid.uuid4())
        self.org_id = org_id
        self.username = username.strip()
        self.email = email.strip()
        self.full_name = full_name.strip()
        self.password_hash = password_hash
        self.invite_code = invite_code or str(uuid.uuid4())[:8].upper()
        self.status = status  # Pending / Approved / Rejected
        self.reviewed_by = reviewed_by
        self.reviewed_at = reviewed_at
        self.created_at = created_at or datetime.now()

    def to_dict(self):
        return {
            "id": self.id,
            "org_id": self.org_id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "invite_code": self.invite_code,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat(),
        }


class Node:
    """
    Represents a registered machine (Node) participating in Federated Learning.
    Each Node belongs to an organization and requires approval to join training.
    """
    def __init__(self, organization_id: str, hostname: str, node_id: str = None, node_name: str = None,
                 os_name: str = "", os_version: str = "", architecture: str = "",
                 cpu_model: str = "", cpu_cores: int = 0, ram_gb: float = 0.0,
                 gpu_available: str = "No", gpu_vendor: str = "", gpu_model: str = "",
                 gpu_count: int = 0, gpu_vram: float = 0.0, cuda_version: str = "",
                 python_version: str = "", flower_version: str = "", conclave_version: str = "",
                 status: str = "Pending", registered_at: datetime = None, last_heartbeat: datetime = None,
                 last_ip: str = "127.0.0.1", public_key: str = None, certificate: str = None,
                 registration_token: str = None, trust_status: str = "Untrusted"):
        import uuid
        self.id = node_id or str(uuid.uuid4())
        self.organization_id = organization_id.strip() if organization_id else ""
        self.hostname = hostname.strip() if hostname else ""
        self.node_name = node_name.strip() if node_name else None
        self.os_name = os_name.strip() if os_name else ""
        self.os_version = os_version.strip() if os_version else ""
        self.architecture = architecture.strip() if architecture else ""
        self.cpu_model = cpu_model.strip() if cpu_model else ""
        self.cpu_cores = cpu_cores or 0
        self.ram_gb = ram_gb or 0.0
        self.gpu_available = gpu_available or "No"
        self.gpu_vendor = gpu_vendor.strip() if gpu_vendor else ""
        self.gpu_model = gpu_model.strip() if gpu_model else ""
        self.gpu_count = gpu_count or 0
        self.gpu_vram = gpu_vram or 0.0
        self.cuda_version = cuda_version.strip() if cuda_version else ""
        self.python_version = python_version.strip() if python_version else ""
        self.flower_version = flower_version.strip() if flower_version else ""
        self.conclave_version = conclave_version.strip() if conclave_version else ""
        self.status = status  # Pending, Approved, Rejected, Revoked, Offline
        self.registered_at = registered_at or datetime.now()
        self.last_heartbeat = last_heartbeat or datetime.now()
        self.last_ip = last_ip.strip() if last_ip else "127.0.0.1"
        self.public_key = public_key
        self.certificate = certificate
        self.registration_token = registration_token
        self.trust_status = trust_status

    def to_dict(self):
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "hostname": self.hostname,
            "node_name": self.node_name,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "cpu_model": self.cpu_model,
            "cpu_cores": self.cpu_cores,
            "ram_gb": self.ram_gb,
            "gpu_available": self.gpu_available,
            "gpu_vendor": self.gpu_vendor,
            "gpu_model": self.gpu_model,
            "gpu_count": self.gpu_count,
            "gpu_vram": self.gpu_vram,
            "cuda_version": self.cuda_version,
            "python_version": self.python_version,
            "flower_version": self.flower_version,
            "conclave_version": self.conclave_version,
            "status": self.status,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_ip": self.last_ip,
            "public_key": self.public_key,
            "certificate": self.certificate,
            "registration_token": self.registration_token,
            "trust_status": self.trust_status
        }


class Notification:
    def __init__(self, type: str, severity: str, title: str, message: str,
                 recipient: str = "all", organization: str = "all",
                 timestamp: datetime = None, read: bool = False, notification_id: str = None):
        self.id = notification_id or str(uuid.uuid4())
        self.type = type.strip()
        self.severity = severity.strip()
        self.title = title.strip()
        self.message = message.strip()
        self.recipient = recipient.strip()
        self.organization = organization.strip()
        self.timestamp = timestamp or datetime.now()
        self.read = read

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "recipient": self.recipient,
            "organization": self.organization,
            "timestamp": self.timestamp.isoformat(),
            "read": self.read
        }


class Report:
    def __init__(self, title: str, generated_by: str, organization: str, date_range: str, summary: dict, detailed_data: list, timestamp: datetime = None, report_id: str = None):
        self.id = report_id or str(uuid.uuid4())
        self.title = title.strip()
        self.generated_by = generated_by.strip()
        self.organization = organization.strip()
        self.date_range = date_range.strip()
        self.summary = summary
        self.detailed_data = detailed_data
        self.timestamp = timestamp or datetime.now()

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "generated_by": self.generated_by,
            "organization": self.organization,
            "date_range": self.date_range,
            "summary": self.summary,
            "detailed_data": self.detailed_data,
            "timestamp": self.timestamp.isoformat()
        }




