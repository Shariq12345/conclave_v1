import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Float, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from conclave.models import Client, Policy, Consent, TrainingSession, AuditEvent, Organization, User, JoinRequest, Node, Notification

DATABASE_FILE = os.getenv("CONCLAVE_DB_FILE", "conclave.db")
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ClientORM(Base):
    __tablename__ = 'clients'
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False)
    registered_at = Column(DateTime, nullable=False)

    def to_domain(self) -> Client:
        return Client(
            name=self.name,
            client_id=self.id,
            status=self.status,
            registered_at=self.registered_at
        )

    @classmethod
    def from_domain(cls, client: Client):
        return cls(
            id=client.id,
            name=client.name,
            status=client.status,
            registered_at=client.registered_at
        )

class PolicyORM(Base):
    __tablename__ = 'policies'
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, default="")
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    secagg_enabled = Column(Integer, default=0) # SQLite does not have native bool column type, store as 0/1 integer
    dp_enabled = Column(Integer, default=0)
    dp_epsilon = Column(Float, default=1.0)
    dp_delta = Column(Float, default=1e-5)

    def to_domain(self) -> Policy:
        return Policy(
            name=self.name,
            description=self.description,
            policy_id=self.id,
            status=self.status,
            created_at=self.created_at,
            secagg_enabled=bool(self.secagg_enabled),
            dp_enabled=bool(self.dp_enabled),
            dp_epsilon=self.dp_epsilon,
            dp_delta=self.dp_delta
        )

    @classmethod
    def from_domain(cls, policy: Policy):
        return cls(
            id=policy.id,
            name=policy.name,
            description=policy.description,
            status=policy.status,
            created_at=policy.created_at,
            secagg_enabled=1 if policy.secagg_enabled else 0,
            dp_enabled=1 if policy.dp_enabled else 0,
            dp_epsilon=policy.dp_epsilon,
            dp_delta=policy.dp_delta
        )

class ConsentORM(Base):
    __tablename__ = 'consents'
    id = Column(String, primary_key=True)
    client_id = Column(String, nullable=False)
    dataset_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    granted_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    def to_domain(self) -> Consent:
        return Consent(
            client_id=self.client_id,
            dataset_name=self.dataset_name,
            status=self.status,
            consent_id=self.id,
            granted_at=self.granted_at,
            revoked_at=self.revoked_at
        )

    @classmethod
    def from_domain(cls, consent: Consent):
        return cls(
            id=consent.id,
            client_id=consent.client_id,
            dataset_name=consent.dataset_name,
            status=consent.status,
            granted_at=consent.granted_at,
            revoked_at=consent.revoked_at
        )

class TrainingSessionORM(Base):
    __tablename__ = 'training_sessions'
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, default="")
    status = Column(String, nullable=False)
    assigned_policy = Column(String, nullable=False)
    dataset_name = Column(String, nullable=False)
    participating_clients = Column(String, nullable=False) # Comma-separated names
    created_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    priority = Column(String, default="Medium")

    def to_domain(self) -> TrainingSession:
        clients = [c.strip() for c in self.participating_clients.split(",") if c.strip()]
        return TrainingSession(
            name=self.name,
            participating_clients=clients,
            assigned_policy=self.assigned_policy,
            dataset_name=self.dataset_name,
            description=self.description,
            status=self.status,
            session_id=self.id,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            priority=self.priority
        )

    @classmethod
    def from_domain(cls, session: TrainingSession):
        return cls(
            id=session.id,
            name=session.name,
            description=session.description,
            status=session.status,
            assigned_policy=session.assigned_policy,
            dataset_name=session.dataset_name,
            participating_clients=",".join(session.participating_clients),
            created_at=session.created_at,
            started_at=session.started_at,
            completed_at=session.completed_at,
            priority=session.priority
        )

class AuditEventORM(Base):
    __tablename__ = 'audit_events'
    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    event_type = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_name = Column(String, nullable=False)
    action = Column(String, nullable=False)
    status = Column(String, nullable=False)
    message = Column(String, nullable=False)
    hash = Column(String, default="")
    previous_hash = Column(String, default="")

    def to_domain(self) -> AuditEvent:
        return AuditEvent(
            event_type=self.event_type,
            resource_type=self.resource_type,
            resource_name=self.resource_name,
            action=self.action,
            status=self.status,
            message=self.message,
            event_id=self.id,
            timestamp=self.timestamp,
            hash=self.hash,
            previous_hash=self.previous_hash
        )

    @classmethod
    def from_domain(cls, event: AuditEvent):
        return cls(
            id=event.id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            resource_type=event.resource_type,
            resource_name=event.resource_name,
            action=event.action,
            status=event.status,
            message=event.message,
            hash=event.hash or "",
            previous_hash=event.previous_hash or ""
        )

class OrganizationORM(Base):
    __tablename__ = 'organizations'
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, default="")
    organization_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    def to_domain(self) -> Organization:
        return Organization(
            name=self.name,
            organization_type=self.organization_type,
            description=self.description,
            status=self.status,
            org_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at
        )

    @classmethod
    def from_domain(cls, org: Organization):
        return cls(
            id=org.id,
            name=org.name,
            description=org.description,
            organization_type=org.organization_type,
            status=org.status,
            created_at=org.created_at,
            updated_at=org.updated_at
        )

class UserORM(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True)
    organization_id = Column(String, nullable=True)  # Nullable: users start without an org
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Unassigned")
    password_hash = Column(String, nullable=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    def to_domain(self) -> User:
        return User(
            organization_id=self.organization_id,
            username=self.username,
            email=self.email,
            full_name=self.full_name,
            status=self.status,
            user_id=self.id,
            role=self.role or "Unassigned",
            password_hash=self.password_hash,
            last_login=self.last_login,
            created_at=self.created_at,
            updated_at=self.updated_at
        )

    @classmethod
    def from_domain(cls, user: User):
        return cls(
            id=user.id,
            organization_id=user.organization_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            role=getattr(user, 'role', 'Unassigned'),
            password_hash=user.password_hash,
            last_login=user.last_login,
            created_at=user.created_at,
            updated_at=user.updated_at
        )


class JoinRequestORM(Base):
    __tablename__ = 'join_requests'
    id = Column(String, primary_key=True)
    org_id = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    invite_code = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False, default="Pending")
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)

    def to_domain(self) -> JoinRequest:
        return JoinRequest(
            org_id=self.org_id,
            username=self.username,
            email=self.email,
            full_name=self.full_name,
            password_hash=self.password_hash,
            invite_code=self.invite_code,
            status=self.status,
            request_id=self.id,
            reviewed_by=self.reviewed_by,
            reviewed_at=self.reviewed_at,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, req: JoinRequest):
        return cls(
            id=req.id,
            org_id=req.org_id,
            username=req.username,
            email=req.email,
            full_name=req.full_name,
            password_hash=req.password_hash,
            invite_code=req.invite_code,
            status=req.status,
            reviewed_by=req.reviewed_by,
            reviewed_at=req.reviewed_at,
            created_at=req.created_at,
        )

class NodeORM(Base):
    __tablename__ = 'nodes'
    id = Column(String, primary_key=True)
    organization_id = Column(String, nullable=False)
    hostname = Column(String, nullable=False)
    node_name = Column(String, nullable=True)
    os_name = Column(String, nullable=False)
    os_version = Column(String, nullable=False)
    architecture = Column(String, nullable=False)
    cpu_model = Column(String, nullable=False)
    cpu_cores = Column(Integer, nullable=False)
    ram_gb = Column(Float, nullable=False)
    gpu_available = Column(String, nullable=False)
    gpu_vendor = Column(String, nullable=True)
    gpu_model = Column(String, nullable=True)
    gpu_count = Column(Integer, nullable=False)
    gpu_vram = Column(Float, nullable=False)
    cuda_version = Column(String, nullable=True)
    python_version = Column(String, nullable=False)
    flower_version = Column(String, nullable=False)
    conclave_version = Column(String, nullable=False)
    status = Column(String, nullable=False)
    registered_at = Column(DateTime, nullable=False)
    last_heartbeat = Column(DateTime, nullable=False)
    last_ip = Column(String, nullable=False)
    public_key = Column(String, nullable=True)
    certificate = Column(String, nullable=True)
    registration_token = Column(String, nullable=True)
    trust_status = Column(String, nullable=True, default="Untrusted")

    def to_domain(self) -> Node:
        return Node(
            node_id=self.id,
            organization_id=self.organization_id,
            hostname=self.hostname,
            node_name=self.node_name,
            os_name=self.os_name,
            os_version=self.os_version,
            architecture=self.architecture,
            cpu_model=self.cpu_model,
            cpu_cores=self.cpu_cores,
            ram_gb=self.ram_gb,
            gpu_available=self.gpu_available,
            gpu_vendor=self.gpu_vendor,
            gpu_model=self.gpu_model,
            gpu_count=self.gpu_count,
            gpu_vram=self.gpu_vram,
            cuda_version=self.cuda_version,
            python_version=self.python_version,
            flower_version=self.flower_version,
            conclave_version=self.conclave_version,
            status=self.status,
            registered_at=self.registered_at,
            last_heartbeat=self.last_heartbeat,
            last_ip=self.last_ip,
            public_key=self.public_key,
            certificate=self.certificate,
            registration_token=self.registration_token,
            trust_status=self.trust_status
        )

    @classmethod
    def from_domain(cls, n: Node):
        return cls(
            id=n.id,
            organization_id=n.organization_id,
            hostname=n.hostname,
            node_name=n.node_name,
            os_name=n.os_name,
            os_version=n.os_version,
            architecture=n.architecture,
            cpu_model=n.cpu_model,
            cpu_cores=n.cpu_cores,
            ram_gb=n.ram_gb,
            gpu_available=n.gpu_available,
            gpu_vendor=n.gpu_vendor,
            gpu_model=n.gpu_model,
            gpu_count=n.gpu_count,
            gpu_vram=n.gpu_vram,
            cuda_version=n.cuda_version,
            python_version=n.python_version,
            flower_version=n.flower_version,
            conclave_version=n.conclave_version,
            status=n.status,
            registered_at=n.registered_at,
            last_heartbeat=n.last_heartbeat,
            last_ip=n.last_ip,
            public_key=n.public_key,
            certificate=n.certificate,
            registration_token=n.registration_token,
            trust_status=n.trust_status
        )


class NotificationORM(Base):
    __tablename__ = 'notifications'
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    recipient = Column(String, default="all")
    organization = Column(String, default="all")
    timestamp = Column(DateTime, nullable=False)
    is_read = Column(Integer, default=0)

    def to_domain(self) -> Notification:
        return Notification(
            notification_id=self.id,
            type=self.type,
            severity=self.severity,
            title=self.title,
            message=self.message,
            recipient=self.recipient,
            organization=self.organization,
            timestamp=self.timestamp,
            read=bool(self.is_read)
        )

    @classmethod
    def from_domain(cls, notification: Notification):
        return cls(
            id=notification.id,
            type=notification.type,
            severity=notification.severity,
            title=notification.title,
            message=notification.message,
            recipient=notification.recipient,
            organization=notification.organization,
            timestamp=notification.timestamp,
            is_read=1 if notification.read else 0
        )


def init_db():
    Base.metadata.create_all(bind=engine)
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        
        # training_sessions priority column migration
        columns_ts = [col['name'] for col in inspector.get_columns('training_sessions')]
        if 'priority' not in columns_ts:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE training_sessions ADD COLUMN priority VARCHAR DEFAULT 'Medium'"))
                
        # policies columns migration
        columns_pol = [col['name'] for col in inspector.get_columns('policies')]
        with engine.begin() as conn:
            if 'secagg_enabled' not in columns_pol:
                conn.execute(text("ALTER TABLE policies ADD COLUMN secagg_enabled INTEGER DEFAULT 0"))
            if 'dp_enabled' not in columns_pol:
                conn.execute(text("ALTER TABLE policies ADD COLUMN dp_enabled INTEGER DEFAULT 0"))
            if 'dp_epsilon' not in columns_pol:
                conn.execute(text("ALTER TABLE policies ADD COLUMN dp_epsilon FLOAT DEFAULT 1.0"))
            if 'dp_delta' not in columns_pol:
                conn.execute(text("ALTER TABLE policies ADD COLUMN dp_delta FLOAT DEFAULT 1e-5"))

        # audit_events columns migration
        columns_ae = [col['name'] for col in inspector.get_columns('audit_events')]
        with engine.begin() as conn:
            if 'hash' not in columns_ae:
                conn.execute(text("ALTER TABLE audit_events ADD COLUMN hash VARCHAR DEFAULT ''"))
            if 'previous_hash' not in columns_ae:
                conn.execute(text("ALTER TABLE audit_events ADD COLUMN previous_hash VARCHAR DEFAULT ''"))
    except Exception:
        pass

