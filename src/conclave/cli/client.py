import os
import requests
from datetime import datetime
from conclave.models import Client, Policy, Consent, TrainingSession, AuditEvent, Organization, User
from conclave.cli.config import load_server_url

def _server_url() -> str:
    """Always reads the current server URL — picks up changes made during the session."""
    return load_server_url()

class RemoteAPIError(Exception):
    def __init__(self, message: str, validation_result: dict = None):
        super().__init__(message)
        self.validation_result = validation_result


TOKEN_FILE = os.path.expanduser("~/.conclave_token")

def get_headers():
    headers = {}
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                token = f.read().strip()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
    return headers

def get_request_ssl_config() -> dict:
    """Configures requests SSL cert and verification parameters for HTTPS connections."""
    url = _server_url()
    if not url.startswith("https://"):
        return {}

    node_dir = os.path.expanduser("~/.conclave")
    cert_path = os.path.join(node_dir, "node_cert.pem")
    key_path = os.path.join(node_dir, "node_key.pem")
    ca_cert_path = os.path.join(node_dir, "ca_cert.pem")

    config = {}
    if os.path.exists(cert_path) and os.path.exists(key_path):
        config["cert"] = (cert_path, key_path)
    if os.path.exists(ca_cert_path):
        config["verify"] = ca_cert_path
    else:
        config["verify"] = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return config


def get(path: str):
    try:
        r = requests.get(f"{_server_url()}{path}", headers=get_headers(), **get_request_ssl_config())
        if r.status_code == 401:
            raise RemoteAPIError("Authentication required. Please log in using 'auth login'.")
        if r.status_code == 403:
            detail = r.json().get("detail", "Forbidden: you do not have permission to perform this action.")
            raise RemoteAPIError(detail)
        if r.status_code == 200:
            return r.json()
        detail = r.json().get("detail", "Unknown server error")
        raise RemoteAPIError(detail)
    except requests.RequestException as e:
        raise RemoteAPIError(f"Failed to connect to Conclave Server at {_server_url()}: {str(e)}")


def post(path: str, json_data: dict = None, headers: dict = None):
    try:
        req_headers = {**get_headers(), **(headers or {})}
        r = requests.post(f"{_server_url()}{path}", json=json_data, headers=req_headers, **get_request_ssl_config())
        if r.status_code == 401:
            raise RemoteAPIError(r.json().get("detail", "Authentication required. Please log in using 'auth login'."))
        if r.status_code == 403:
            detail = r.json().get("detail", "Forbidden: you do not have permission to perform this action.")
            raise RemoteAPIError(detail)
        if r.status_code in (200, 201):
            return r.json()
        err_data = r.json()
        detail = err_data.get("detail", "Unknown server error")
        val_result = err_data.get("validation_result")
        raise RemoteAPIError(detail, val_result)
    except requests.RequestException as e:
        raise RemoteAPIError(f"Failed to connect to Conclave Server at {_server_url()}: {str(e)}")


def delete(path: str):
    try:
        r = requests.delete(f"{_server_url()}{path}", headers=get_headers(), **get_request_ssl_config())
        if r.status_code == 401:
            raise RemoteAPIError("Authentication required. Please log in using 'auth login'.")
        if r.status_code == 403:
            detail = r.json().get("detail", "Forbidden: you do not have permission to perform this action.")
            raise RemoteAPIError(detail)
        if r.status_code == 200:
            return r.json()
        detail = r.json().get("detail", "Unknown server error")
        raise RemoteAPIError(detail)
    except requests.RequestException as e:
        raise RemoteAPIError(f"Failed to connect to Conclave Server at {_server_url()}: {str(e)}")


# Parser Helpers
def to_client(d: dict) -> Client:
    reg_at = datetime.fromisoformat(d["registered_at"]) if isinstance(d["registered_at"], str) else d["registered_at"]
    return Client(name=d["name"], client_id=d["id"], status=d["status"], registered_at=reg_at)


def to_policy(d: dict) -> Policy:
    created = datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"]
    return Policy(
        name=d["name"],
        description=d["description"],
        policy_id=d["id"],
        status=d["status"],
        created_at=created,
        secagg_enabled=d.get("secagg_enabled", False),
        dp_enabled=d.get("dp_enabled", False),
        dp_epsilon=d.get("dp_epsilon", 1.0),
        dp_delta=d.get("dp_delta", 1e-5)
    )


def to_consent(d: dict) -> Consent:
    granted = datetime.fromisoformat(d["granted_at"]) if isinstance(d["granted_at"], str) else d["granted_at"]
    revoked = None
    if d.get("revoked_at"):
        revoked = datetime.fromisoformat(d["revoked_at"]) if isinstance(d["revoked_at"], str) else d["revoked_at"]
    return Consent(client_id=d["client_id"], dataset_name=d["dataset_name"], status=d["status"], consent_id=d["id"], granted_at=granted, revoked_at=revoked)


def to_training(d: dict) -> TrainingSession:
    created = datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"]
    started = None
    if d.get("started_at"):
        started = datetime.fromisoformat(d["started_at"]) if isinstance(d["started_at"], str) else d["started_at"]
    completed = None
    if d.get("completed_at"):
        completed = datetime.fromisoformat(d["completed_at"]) if isinstance(d["completed_at"], str) else d["completed_at"]
    return TrainingSession(
        name=d["name"],
        participating_clients=d["participating_clients"],
        assigned_policy=d["assigned_policy"],
        dataset_name=d["dataset_name"],
        description=d["description"],
        status=d["status"],
        session_id=d["id"],
        created_at=created,
        started_at=started,
        completed_at=completed,
        priority=d.get("priority", "Medium")
    )


def to_audit(d: dict) -> AuditEvent:
    ts = datetime.fromisoformat(d["timestamp"]) if isinstance(d["timestamp"], str) else d["timestamp"]
    return AuditEvent(
        event_type=d["event_type"],
        resource_type=d["resource_type"],
        resource_name=d["resource_name"],
        action=d["action"],
        status=d["status"],
        message=d["message"],
        event_id=d["id"],
        timestamp=ts,
        hash=d.get("hash"),
        previous_hash=d.get("previous_hash")
    )


def to_organization(d: dict) -> Organization:
    created = datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"]
    updated = datetime.fromisoformat(d["updated_at"]) if isinstance(d["updated_at"], str) else d["updated_at"]
    return Organization(
        name=d["name"],
        organization_type=d["organization_type"],
        description=d["description"],
        status=d["status"],
        org_id=d["id"],
        created_at=created,
        updated_at=updated
    )


def to_user(d: dict) -> User:
    created = datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"]
    updated = datetime.fromisoformat(d["updated_at"]) if isinstance(d["updated_at"], str) else d["updated_at"]
    last_login = None
    if d.get("last_login"):
        last_login = datetime.fromisoformat(d["last_login"]) if isinstance(d["last_login"], str) else d["last_login"]
    return User(
        organization_id=d["organization_id"],
        username=d["username"],
        email=d["email"],
        full_name=d["full_name"],
        status=d["status"],
        user_id=d["id"],
        role=d.get("role", "Operator"),
        last_login=last_login,
        created_at=created,
        updated_at=updated,
    )


