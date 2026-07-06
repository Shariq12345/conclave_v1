import threading
from typing import List, Optional
from conclave.models import Client, Policy, AuditEvent, Consent, TrainingSession, Organization, User, JoinRequest, Node, Notification

class ClientRepository:
    def save(self, client: Client) -> Client:
        raise NotImplementedError
        
    def find_all(self) -> List[Client]:
        raise NotImplementedError
        
    def find_by_name(self, name: str) -> Optional[Client]:
        raise NotImplementedError
        
    def delete_by_name(self, name: str) -> bool:
        raise NotImplementedError

class InMemoryClientRepository(ClientRepository):
    def __init__(self):
        self._lock = threading.Lock()
        self._clients = {}  # key: lowercase name, value: Client

    def save(self, client: Client) -> Client:
        with self._lock:
            self._clients[client.name.lower()] = client
            return client

    def find_all(self) -> List[Client]:
        with self._lock:
            return sorted(self._clients.values(), key=lambda c: c.registered_at)

    def find_by_name(self, name: str) -> Optional[Client]:
        with self._lock:
            return self._clients.get(name.lower())

    def delete_by_name(self, name: str) -> bool:
        with self._lock:
            key = name.lower()
            if key in self._clients:
                del self._clients[key]
                return True
            return False

class PolicyRepository:
    def save(self, policy: Policy) -> Policy:
        raise NotImplementedError
        
    def find_all(self) -> List[Policy]:
        raise NotImplementedError
        
    def find_by_name(self, name: str) -> Optional[Policy]:
        raise NotImplementedError
        
    def delete_by_name(self, name: str) -> bool:
        raise NotImplementedError

class InMemoryPolicyRepository(PolicyRepository):
    def __init__(self):
        self._lock = threading.Lock()
        self._policies = {}  # key: lowercase name, value: Policy

    def save(self, policy: Policy) -> Policy:
        with self._lock:
            self._policies[policy.name.lower()] = policy
            return policy

    def find_all(self) -> List[Policy]:
        with self._lock:
            return sorted(self._policies.values(), key=lambda p: p.created_at)

    def find_by_name(self, name: str) -> Optional[Policy]:
        with self._lock:
            return self._policies.get(name.lower())

    def delete_by_name(self, name: str) -> bool:
        with self._lock:
            key = name.lower()
            if key in self._policies:
                del self._policies[key]
                return True
            return False

class AuditRepository:
    def save(self, event: AuditEvent) -> AuditEvent:
        raise NotImplementedError
        
    def find_all(self) -> List[AuditEvent]:
        raise NotImplementedError

    def find_by_id(self, event_id: str) -> Optional[AuditEvent]:
        raise NotImplementedError

    def clear(self):
        raise NotImplementedError

    def find_last_event(self) -> Optional[AuditEvent]:
        raise NotImplementedError

class InMemoryAuditRepository(AuditRepository):
    def __init__(self):
        self._lock = threading.Lock()
        self._events = {}  # key: event_id, value: AuditEvent
        self._list = []    # track insertion order

    def save(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self._events[event.id] = event
            self._list.append(event)
            return event

    def find_last_event(self) -> Optional[AuditEvent]:
        with self._lock:
            if not self._list:
                return None
            return self._list[-1]

    def find_all(self) -> List[AuditEvent]:
        with self._lock:
            return list(reversed(self._list))

    def find_by_id(self, event_id: str) -> Optional[AuditEvent]:
        with self._lock:
            if event_id in self._events:
                return self._events[event_id]
            if len(event_id) >= 8:
                matches = [e for e in self._list if e.id.startswith(event_id)]
                if len(matches) == 1:
                    return matches[0]
            return None

    def clear(self):
        with self._lock:
            self._events.clear()
            self._list.clear()

class ConsentRepository:
    def save(self, consent: Consent) -> Consent:
        raise NotImplementedError
    def find_all(self) -> List[Consent]:
        raise NotImplementedError
    def find_by_client_and_dataset(self, client_id: str, dataset_name: str) -> Optional[Consent]:
        raise NotImplementedError
    def find_by_client(self, client_id: str) -> List[Consent]:
        raise NotImplementedError

class InMemoryConsentRepository(ConsentRepository):
    def __init__(self):
        self._lock = threading.Lock()
        self._consents = {}  # key: (client_id, dataset_name.lower()), value: Consent

    def save(self, consent: Consent) -> Consent:
        with self._lock:
            key = (consent.client_id, consent.dataset_name.lower())
            self._consents[key] = consent
            return consent

    def find_all(self) -> List[Consent]:
        with self._lock:
            return sorted(self._consents.values(), key=lambda c: c.granted_at)

    def find_by_client_and_dataset(self, client_id: str, dataset_name: str) -> Optional[Consent]:
        with self._lock:
            key = (client_id, dataset_name.lower())
            return self._consents.get(key)

    def find_by_client(self, client_id: str) -> List[Consent]:
        with self._lock:
            return [c for c in self._consents.values() if c.client_id == client_id]


class TrainingRepository:
    def save(self, session: TrainingSession) -> TrainingSession:
        raise NotImplementedError
        
    def find_all(self) -> List[TrainingSession]:
        raise NotImplementedError
        
    def find_by_name(self, name: str) -> Optional[TrainingSession]:
        raise NotImplementedError
        
    def delete_by_name(self, name: str) -> bool:
        raise NotImplementedError

class InMemoryTrainingRepository(TrainingRepository):
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}  # key: lowercase name, value: TrainingSession

    def save(self, session: TrainingSession) -> TrainingSession:
        with self._lock:
            self._sessions[session.name.lower()] = session
            return session

    def find_all(self) -> List[TrainingSession]:
        with self._lock:
            return sorted(self._sessions.values(), key=lambda s: s.created_at)

    def find_by_name(self, name: str) -> Optional[TrainingSession]:
        with self._lock:
            return self._sessions.get(name.lower())

    def delete_by_name(self, name: str) -> bool:
        with self._lock:
            key = name.lower()
            if key in self._sessions:
                del self._sessions[key]
                return True
            return False


from conclave.server.database import (
    ClientORM, PolicyORM, ConsentORM, TrainingSessionORM, AuditEventORM, OrganizationORM, UserORM
)

class SQLiteClientRepository(ClientRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, client: Client) -> Client:
        with self.session_factory() as session:
            orm_client = session.query(ClientORM).filter_by(id=client.id).first()
            if not orm_client:
                orm_client = session.query(ClientORM).filter(ClientORM.name.ilike(client.name)).first()
            
            if orm_client:
                orm_client.name = client.name
                orm_client.status = client.status
                orm_client.registered_at = client.registered_at
            else:
                orm_client = ClientORM.from_domain(client)
                session.add(orm_client)
            session.commit()
            return client

    def find_all(self) -> List[Client]:
        with self.session_factory() as session:
            orm_clients = session.query(ClientORM).order_by(ClientORM.registered_at).all()
            return [c.to_domain() for c in orm_clients]

    def find_by_name(self, name: str) -> Optional[Client]:
        with self.session_factory() as session:
            orm_client = session.query(ClientORM).filter(ClientORM.name.ilike(name)).first()
            return orm_client.to_domain() if orm_client else None

    def delete_by_name(self, name: str) -> bool:
        with self.session_factory() as session:
            orm_client = session.query(ClientORM).filter(ClientORM.name.ilike(name)).first()
            if orm_client:
                session.delete(orm_client)
                session.commit()
                return True
            return False

class SQLitePolicyRepository(PolicyRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, policy: Policy) -> Policy:
        with self.session_factory() as session:
            orm_policy = session.query(PolicyORM).filter_by(id=policy.id).first()
            if not orm_policy:
                orm_policy = session.query(PolicyORM).filter(PolicyORM.name.ilike(policy.name)).first()
            
            if orm_policy:
                orm_policy.name = policy.name
                orm_policy.description = policy.description
                orm_policy.status = policy.status
                orm_policy.created_at = policy.created_at
            else:
                orm_policy = PolicyORM.from_domain(policy)
                session.add(orm_policy)
            session.commit()
            return policy

    def find_all(self) -> List[Policy]:
        with self.session_factory() as session:
            orm_policies = session.query(PolicyORM).order_by(PolicyORM.created_at).all()
            return [p.to_domain() for p in orm_policies]

    def find_by_name(self, name: str) -> Optional[Policy]:
        with self.session_factory() as session:
            orm_policy = session.query(PolicyORM).filter(PolicyORM.name.ilike(name)).first()
            return orm_policy.to_domain() if orm_policy else None

    def delete_by_name(self, name: str) -> bool:
        with self.session_factory() as session:
            orm_policy = session.query(PolicyORM).filter(PolicyORM.name.ilike(name)).first()
            if orm_policy:
                session.delete(orm_policy)
                session.commit()
                return True
            return False

class SQLiteConsentRepository(ConsentRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, consent: Consent) -> Consent:
        with self.session_factory() as session:
            orm_consent = session.query(ConsentORM).filter_by(id=consent.id).first()
            if not orm_consent:
                orm_consent = session.query(ConsentORM).filter_by(
                    client_id=consent.client_id,
                    dataset_name=consent.dataset_name
                ).first()
            
            if orm_consent:
                orm_consent.status = consent.status
                orm_consent.granted_at = consent.granted_at
                orm_consent.revoked_at = consent.revoked_at
            else:
                orm_consent = ConsentORM.from_domain(consent)
                session.add(orm_consent)
            session.commit()
            return consent

    def find_all(self) -> List[Consent]:
        with self.session_factory() as session:
            orm_consents = session.query(ConsentORM).order_by(ConsentORM.granted_at).all()
            return [c.to_domain() for c in orm_consents]

    def find_by_client_and_dataset(self, client_id: str, dataset_name: str) -> Optional[Consent]:
        with self.session_factory() as session:
            orm_consent = session.query(ConsentORM).filter(
                ConsentORM.client_id == client_id,
                ConsentORM.dataset_name.ilike(dataset_name)
            ).first()
            return orm_consent.to_domain() if orm_consent else None

    def find_by_client(self, client_id: str) -> List[Consent]:
        with self.session_factory() as session:
            orm_consents = session.query(ConsentORM).filter_by(client_id=client_id).all()
            return [c.to_domain() for c in orm_consents]

class SQLiteTrainingRepository(TrainingRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, session_obj: TrainingSession) -> TrainingSession:
        with self.session_factory() as session:
            orm_session = session.query(TrainingSessionORM).filter_by(id=session_obj.id).first()
            if not orm_session:
                orm_session = session.query(TrainingSessionORM).filter(TrainingSessionORM.name.ilike(session_obj.name)).first()
            
            if orm_session:
                orm_session.name = session_obj.name
                orm_session.description = session_obj.description
                orm_session.status = session_obj.status
                orm_session.assigned_policy = session_obj.assigned_policy
                orm_session.dataset_name = session_obj.dataset_name
                orm_session.participating_clients = ",".join(session_obj.participating_clients)
                orm_session.created_at = session_obj.created_at
                orm_session.started_at = session_obj.started_at
                orm_session.completed_at = session_obj.completed_at
            else:
                orm_session = TrainingSessionORM.from_domain(session_obj)
                session.add(orm_session)
            session.commit()
            return session_obj

    def find_all(self) -> List[TrainingSession]:
        with self.session_factory() as session:
            orm_sessions = session.query(TrainingSessionORM).order_by(TrainingSessionORM.created_at).all()
            return [s.to_domain() for s in orm_sessions]

    def find_by_name(self, name: str) -> Optional[TrainingSession]:
        with self.session_factory() as session:
            orm_session = session.query(TrainingSessionORM).filter(TrainingSessionORM.name.ilike(name)).first()
            return orm_session.to_domain() if orm_session else None

    def delete_by_name(self, name: str) -> bool:
        with self.session_factory() as session:
            orm_session = session.query(TrainingSessionORM).filter(TrainingSessionORM.name.ilike(name)).first()
            if orm_session:
                session.delete(orm_session)
                session.commit()
                return True
            return False

class SQLiteAuditRepository(AuditRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, event: AuditEvent) -> AuditEvent:
        with self.session_factory() as session:
            orm_event = AuditEventORM.from_domain(event)
            session.add(orm_event)
            session.commit()
            return event

    def find_last_event(self) -> Optional[AuditEvent]:
        from sqlalchemy import text
        with self.session_factory() as session:
            orm_event = session.query(AuditEventORM).order_by(text("rowid DESC")).first()
            if orm_event:
                return orm_event.to_domain()
            return None

    def find_all(self) -> List[AuditEvent]:
        from sqlalchemy import text
        with self.session_factory() as session:
            orm_events = session.query(AuditEventORM).order_by(text("rowid DESC")).all()
            return [e.to_domain() for e in orm_events]

    def find_by_id(self, event_id: str) -> Optional[AuditEvent]:
        with self.session_factory() as session:
            orm_event = session.query(AuditEventORM).filter_by(id=event_id).first()
            if orm_event:
                return orm_event.to_domain()
            if len(event_id) >= 8:
                orm_events = session.query(AuditEventORM).filter(AuditEventORM.id.like(f"{event_id}%")).all()
                if len(orm_events) == 1:
                    return orm_events[0].to_domain()
            return None

    def clear(self):
        with self.session_factory() as session:
            session.query(AuditEventORM).delete()
            session.commit()

class OrganizationRepository:
    def save(self, org: Organization) -> Organization:
        raise NotImplementedError
        
    def find_all(self) -> List[Organization]:
        raise NotImplementedError
        
    def find_by_name(self, name: str) -> Optional[Organization]:
        raise NotImplementedError
        
    def delete_by_name(self, name: str) -> bool:
        raise NotImplementedError

class SQLiteOrganizationRepository(OrganizationRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, org: Organization) -> Organization:
        with self.session_factory() as session:
            orm_org = session.query(OrganizationORM).filter_by(id=org.id).first()
            if not orm_org:
                orm_org = session.query(OrganizationORM).filter(OrganizationORM.name.ilike(org.name)).first()
            
            if orm_org:
                orm_org.name = org.name
                orm_org.description = org.description
                orm_org.organization_type = org.organization_type
                orm_org.status = org.status
                orm_org.updated_at = org.updated_at
            else:
                orm_org = OrganizationORM.from_domain(org)
                session.add(orm_org)
            session.commit()
            return org

    def find_all(self) -> List[Organization]:
        with self.session_factory() as session:
            orm_orgs = session.query(OrganizationORM).order_by(OrganizationORM.created_at).all()
            return [o.to_domain() for o in orm_orgs]

    def find_by_name(self, name: str) -> Optional[Organization]:
        with self.session_factory() as session:
            orm_org = session.query(OrganizationORM).filter(OrganizationORM.name.ilike(name)).first()
            return orm_org.to_domain() if orm_org else None

    def delete_by_name(self, name: str) -> bool:
        with self.session_factory() as session:
            orm_org = session.query(OrganizationORM).filter(OrganizationORM.name.ilike(name)).first()
            if orm_org:
                session.delete(orm_org)
                session.commit()
                return True
            return False

class UserRepository:
    def save(self, user: User) -> User:
        raise NotImplementedError
        
    def find_all(self) -> List[User]:
        raise NotImplementedError
        
    def find_by_username(self, username: str) -> Optional[User]:
        raise NotImplementedError

    def find_by_email(self, email: str) -> Optional[User]:
        raise NotImplementedError
        
    def delete_by_username(self, username: str) -> bool:
        raise NotImplementedError

class SQLiteUserRepository(UserRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, user: User) -> User:
        with self.session_factory() as session:
            orm_user = session.query(UserORM).filter_by(id=user.id).first()
            if not orm_user:
                orm_user = session.query(UserORM).filter(UserORM.username.ilike(user.username)).first()
            
            if orm_user:
                orm_user.organization_id = user.organization_id
                orm_user.username = user.username
                orm_user.email = user.email
                orm_user.full_name = user.full_name
                orm_user.status = user.status
                orm_user.role = getattr(user, 'role', 'Operator')
                orm_user.password_hash = user.password_hash
                orm_user.last_login = user.last_login
                orm_user.updated_at = user.updated_at
                
                # Copy new security fields
                orm_user.email_verified = 1 if user.email_verified else 0
                orm_user.email_verification_token = user.email_verification_token
                orm_user.password_reset_token = user.password_reset_token
                orm_user.password_reset_expires = user.password_reset_expires
                orm_user.mfa_enabled = 1 if user.mfa_enabled else 0
                orm_user.mfa_secret = user.mfa_secret
                orm_user.mfa_backup_codes = user.mfa_backup_codes
            else:
                orm_user = UserORM.from_domain(user)
                session.add(orm_user)
            session.commit()
            return user

    def find_all(self) -> List[User]:
        with self.session_factory() as session:
            orm_users = session.query(UserORM).order_by(UserORM.created_at).all()
            return [u.to_domain() for u in orm_users]

    def find_by_username(self, username: str) -> Optional[User]:
        with self.session_factory() as session:
            orm_user = session.query(UserORM).filter(UserORM.username.ilike(username)).first()
            return orm_user.to_domain() if orm_user else None

    def find_by_email(self, email: str) -> Optional[User]:
        with self.session_factory() as session:
            orm_user = session.query(UserORM).filter(UserORM.email.ilike(email)).first()
            return orm_user.to_domain() if orm_user else None

    def delete_by_username(self, username: str) -> bool:
        with self.session_factory() as session:
            orm_user = session.query(UserORM).filter(UserORM.username.ilike(username)).first()
            if orm_user:
                session.delete(orm_user)
                session.commit()
                return True
            return False


# ── JoinRequest Repository ────────────────────────────────────────────────────

class JoinRequestRepository:
    def save(self, req) -> object:
        raise NotImplementedError

    def find_by_id(self, request_id: str) -> Optional[object]:
        raise NotImplementedError

    def find_by_invite_code(self, code: str) -> Optional[object]:
        raise NotImplementedError

    def find_pending_by_org(self, org_id: str) -> List[object]:
        raise NotImplementedError

    def find_by_username(self, username: str) -> Optional[object]:
        raise NotImplementedError


class SQLiteJoinRequestRepository(JoinRequestRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, req: JoinRequest) -> JoinRequest:
        from conclave.server.database import JoinRequestORM
        with self.session_factory() as session:
            orm = session.query(JoinRequestORM).filter_by(id=req.id).first()
            if orm:
                orm.status = req.status
                orm.reviewed_by = req.reviewed_by
                orm.reviewed_at = req.reviewed_at
            else:
                orm = JoinRequestORM.from_domain(req)
                session.add(orm)
            session.commit()
            return req

    def find_by_id(self, request_id: str) -> Optional[JoinRequest]:
        from conclave.server.database import JoinRequestORM
        with self.session_factory() as session:
            orm = session.query(JoinRequestORM).filter_by(id=request_id).first()
            return orm.to_domain() if orm else None

    def find_by_invite_code(self, code: str) -> Optional[JoinRequest]:
        from conclave.server.database import JoinRequestORM
        with self.session_factory() as session:
            orm = session.query(JoinRequestORM).filter_by(invite_code=code.upper()).first()
            return orm.to_domain() if orm else None

    def find_pending_by_org(self, org_id: str) -> List[JoinRequest]:
        from conclave.server.database import JoinRequestORM
        with self.session_factory() as session:
            orms = session.query(JoinRequestORM).filter_by(
                org_id=org_id, status="Pending"
            ).order_by(JoinRequestORM.created_at).all()
            return [o.to_domain() for o in orms]

    def find_by_username(self, username: str) -> Optional[JoinRequest]:
        from conclave.server.database import JoinRequestORM
        with self.session_factory() as session:
            orm = session.query(JoinRequestORM).filter(
                JoinRequestORM.username.ilike(username)
            ).first()
            return orm.to_domain() if orm else None


class NodeRepository:
    def save(self, node: Node) -> Node:
        raise NotImplementedError

    def find_all(self) -> List[Node]:
        raise NotImplementedError

    def find_by_id(self, node_id: str) -> Optional[Node]:
        raise NotImplementedError

    def find_by_org(self, org_id: str) -> List[Node]:
        raise NotImplementedError

    def delete_by_id(self, node_id: str) -> bool:
        raise NotImplementedError


class SQLiteNodeRepository(NodeRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, node: Node) -> Node:
        from conclave.server.database import NodeORM
        with self.session_factory() as session:
            orm = session.query(NodeORM).filter_by(id=node.id).first()
            if orm:
                orm.hostname = node.hostname
                orm.node_name = node.node_name
                orm.os_name = node.os_name
                orm.os_version = node.os_version
                orm.architecture = node.architecture
                orm.cpu_model = node.cpu_model
                orm.cpu_cores = node.cpu_cores
                orm.ram_gb = node.ram_gb
                orm.gpu_available = node.gpu_available
                orm.gpu_vendor = node.gpu_vendor
                orm.gpu_model = node.gpu_model
                orm.gpu_count = node.gpu_count
                orm.gpu_vram = node.gpu_vram
                orm.cuda_version = node.cuda_version
                orm.python_version = node.python_version
                orm.flower_version = node.flower_version
                orm.conclave_version = node.conclave_version
                orm.status = node.status
                orm.last_heartbeat = node.last_heartbeat
                orm.last_ip = node.last_ip
                orm.public_key = node.public_key
                orm.certificate = node.certificate
                orm.registration_token = node.registration_token
                orm.trust_status = node.trust_status
            else:
                orm = NodeORM.from_domain(node)
                session.add(orm)
            session.commit()
            return node

    def find_all(self) -> List[Node]:
        from conclave.server.database import NodeORM
        with self.session_factory() as session:
            orms = session.query(NodeORM).order_by(NodeORM.registered_at).all()
            return [o.to_domain() for o in orms]

    def find_by_id(self, node_id: str) -> Optional[Node]:
        from conclave.server.database import NodeORM
        with self.session_factory() as session:
            orm = session.query(NodeORM).filter_by(id=node_id).first()
            return orm.to_domain() if orm else None

    def find_by_org(self, org_id: str) -> List[Node]:
        from conclave.server.database import NodeORM
        with self.session_factory() as session:
            orms = session.query(NodeORM).filter_by(organization_id=org_id).order_by(NodeORM.registered_at).all()
            return [o.to_domain() for o in orms]

    def delete_by_id(self, node_id: str) -> bool:
        from conclave.server.database import NodeORM
        with self.session_factory() as session:
            orm = session.query(NodeORM).filter_by(id=node_id).first()
            if orm:
                session.delete(orm)
                session.commit()
                return True
            return False


class NotificationRepository:
    def save(self, notification: Notification) -> Notification:
        raise NotImplementedError

    def find_all(self) -> List[Notification]:
        raise NotImplementedError

    def find_unread(self) -> List[Notification]:
        raise NotImplementedError

    def mark_as_read(self, notification_id: str) -> bool:
        raise NotImplementedError

    def mark_all_read(self) -> int:
        raise NotImplementedError


class SQLiteNotificationRepository(NotificationRepository):
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def save(self, notification: Notification) -> Notification:
        from conclave.server.database import NotificationORM
        with self.session_factory() as session:
            orm = session.query(NotificationORM).filter_by(id=notification.id).first()
            if orm:
                orm.type = notification.type
                orm.severity = notification.severity
                orm.title = notification.title
                orm.message = notification.message
                orm.recipient = notification.recipient
                orm.organization = notification.organization
                orm.timestamp = notification.timestamp
                orm.is_read = 1 if notification.read else 0
            else:
                orm = NotificationORM.from_domain(notification)
                session.add(orm)
            session.commit()
            return notification

    def find_all(self) -> List[Notification]:
        from conclave.server.database import NotificationORM
        with self.session_factory() as session:
            orms = session.query(NotificationORM).order_by(NotificationORM.timestamp.desc()).all()
            return [o.to_domain() for o in orms]

    def find_unread(self) -> List[Notification]:
        from conclave.server.database import NotificationORM
        with self.session_factory() as session:
            orms = session.query(NotificationORM).filter_by(is_read=0).order_by(NotificationORM.timestamp.desc()).all()
            return [o.to_domain() for o in orms]

    def mark_as_read(self, notification_id: str) -> bool:
        from conclave.server.database import NotificationORM
        with self.session_factory() as session:
            orm = session.query(NotificationORM).filter_by(id=notification_id).first()
            if orm:
                orm.is_read = 1
                session.commit()
                return True
            return False

    def mark_all_read(self) -> int:
        from conclave.server.database import NotificationORM
        with self.session_factory() as session:
            orms = session.query(NotificationORM).filter_by(is_read=0).all()
            count = len(orms)
            for orm in orms:
                orm.is_read = 1
            session.commit()
            return count


