class ServiceRegistry:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceRegistry, cls).__new__(cls)
            
            # Lazily initialize database connection and create tables
            from conclave.server.database import init_db, SessionLocal
            init_db()
            cls._instance._session_factory = SessionLocal
            
            cls._instance._client_repository = None
            cls._instance._client_service = None
            cls._instance._policy_repository = None
            cls._instance._policy_service = None
            cls._instance._audit_repository = None
            cls._instance._audit_service = None
            cls._instance._consent_repository = None
            cls._instance._consent_service = None
            cls._instance._training_repository = None
            cls._instance._training_service = None
            cls._instance._governance_service = None
            cls._instance._organization_repository = None
            cls._instance._organization_service = None
            cls._instance._user_repository = None
            cls._instance._user_service = None
            cls._instance._auth_service = None
            cls._instance._join_request_repository = None
            cls._instance._onboarding_service = None
            cls._instance._node_repository = None
            cls._instance._node_service = None
            cls._instance._monitoring_service = None
            cls._instance._notification_repository = None
            cls._instance._notification_service = None
            cls._instance._notification_hub = None
            cls._instance._reporting_service = None
            cls._instance._compliance_service = None
            
            # Start background monitoring daemon
            cls._instance.monitoring_service.start_background_monitor()
        return cls._instance

    @property
    def client_repository(self):
        if self._client_repository is None:
            from conclave.server.storage import SQLiteClientRepository
            self._client_repository = SQLiteClientRepository(self._session_factory)
        return self._client_repository

    @property
    def client_service(self):
        if self._client_service is None:
            from conclave.server.services import ClientService
            self._client_service = ClientService(self.client_repository, self.audit_service)
        return self._client_service

    @property
    def audit_repository(self):
        if self._audit_repository is None:
            from conclave.server.storage import SQLiteAuditRepository
            self._audit_repository = SQLiteAuditRepository(self._session_factory)
        return self._audit_repository

    @property
    def audit_service(self):
        if self._audit_service is None:
            from conclave.server.services import AuditService
            self._audit_service = AuditService(self.audit_repository)
        return self._audit_service

    @property
    def policy_repository(self):
        if self._policy_repository is None:
            from conclave.server.storage import SQLitePolicyRepository
            self._policy_repository = SQLitePolicyRepository(self._session_factory)
        return self._policy_repository

    @property
    def policy_service(self):
        if self._policy_service is None:
            from conclave.server.services import PolicyService
            self._policy_service = PolicyService(self.policy_repository, self.audit_service)
        return self._policy_service

    @property
    def consent_repository(self):
        if self._consent_repository is None:
            from conclave.server.storage import SQLiteConsentRepository
            self._consent_repository = SQLiteConsentRepository(self._session_factory)
        return self._consent_repository

    @property
    def consent_service(self):
        if self._consent_service is None:
            from conclave.server.services import ConsentService
            self._consent_service = ConsentService(self.consent_repository, self.client_service, self.audit_service)
        return self._consent_service

    @property
    def governance_service(self):
        if self._governance_service is None:
            from conclave.server.services import GovernanceService
            self._governance_service = GovernanceService(self.client_service, self.policy_service, self.consent_service)
        return self._governance_service

    @property
    def training_repository(self):
        if self._training_repository is None:
            from conclave.server.storage import SQLiteTrainingRepository
            self._training_repository = SQLiteTrainingRepository(self._session_factory)
        return self._training_repository

    @property
    def training_service(self):
        if self._training_service is None:
            from conclave.server.services import TrainingService
            from conclave.server.orchestrator import TrainingOrchestrator
            orch = TrainingOrchestrator(
                self.node_service,
                self.governance_service,
                self.audit_service,
                self.training_repository
            )
            self._training_service = TrainingService(
                self.training_repository,
                self.governance_service,
                orch,
                self.audit_service
            )
        return self._training_service

    @property
    def organization_repository(self):
        if self._organization_repository is None:
            from conclave.server.storage import SQLiteOrganizationRepository
            self._organization_repository = SQLiteOrganizationRepository(self._session_factory)
        return self._organization_repository

    @property
    def organization_service(self):
        if self._organization_service is None:
            from conclave.server.services import OrganizationService
            self._organization_service = OrganizationService(self.organization_repository, self.audit_service)
        return self._organization_service

    @property
    def user_repository(self):
        if self._user_repository is None:
            from conclave.server.storage import SQLiteUserRepository
            self._user_repository = SQLiteUserRepository(self._session_factory)
        return self._user_repository

    @property
    def user_service(self):
        if self._user_service is None:
            from conclave.server.services import UserService
            self._user_service = UserService(self.user_repository, self.organization_repository, self.audit_service)
        return self._user_service

    @property
    def auth_service(self):
        if self._auth_service is None:
            from conclave.server.services import AuthService
            self._auth_service = AuthService(self.user_service, self.audit_service)
        return self._auth_service

    @property
    def join_request_repository(self):
        if self._join_request_repository is None:
            from conclave.server.storage import SQLiteJoinRequestRepository
            self._join_request_repository = SQLiteJoinRequestRepository(self._session_factory)
        return self._join_request_repository

    @property
    def onboarding_service(self):
        if self._onboarding_service is None:
            from conclave.server.services import OnboardingService
            self._onboarding_service = OnboardingService(
                org_service=self.organization_service,
                user_service=self.user_service,
                auth_service=self.auth_service,
                join_request_repository=self.join_request_repository,
                audit_service=self.audit_service,
            )
        return self._onboarding_service

    @property
    def node_repository(self):
        if self._node_repository is None:
            from conclave.server.storage import SQLiteNodeRepository
            self._node_repository = SQLiteNodeRepository(self._session_factory)
        return self._node_repository

    @property
    def node_service(self):
        if self._node_service is None:
            from conclave.server.services import NodeService
            self._node_service = NodeService(self.node_repository, self.audit_service)
        return self._node_service

    @property
    def monitoring_service(self):
        if self._monitoring_service is None:
            from conclave.server.monitoring import MonitoringService
            self._monitoring_service = MonitoringService(self)
        return self._monitoring_service

    @property
    def notification_repository(self):
        if self._notification_repository is None:
            from conclave.server.storage import SQLiteNotificationRepository
            self._notification_repository = SQLiteNotificationRepository(self._session_factory)
        return self._notification_repository

    @property
    def notification_service(self):
        if self._notification_service is None:
            from conclave.server.services import NotificationService
            self._notification_service = NotificationService(self.notification_repository, self.audit_service)
        return self._notification_service

    @property
    def notification_hub(self):
        if self._notification_hub is None:
            from conclave.server.notifications import (
                NotificationHub,
                DatabaseNotificationChannel,
                SlackNotificationChannel,
                EmailNotificationChannel,
                WebSocketNotificationChannel
            )
            hub = NotificationHub()
            hub.register_channel(DatabaseNotificationChannel(self.notification_repository))
            hub.register_channel(SlackNotificationChannel())
            hub.register_channel(EmailNotificationChannel())
            hub.register_channel(WebSocketNotificationChannel())
            self._notification_hub = hub
        return self._notification_hub

    @property
    def reporting_service(self):
        if self._reporting_service is None:
            from conclave.server.reporting import ReportingService
            self._reporting_service = ReportingService(self)
        return self._reporting_service

    @property
    def compliance_service(self):
        if self._compliance_service is None:
            from conclave.server.compliance import ComplianceService
            self._compliance_service = ComplianceService(self)
        return self._compliance_service



