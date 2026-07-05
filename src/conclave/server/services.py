from typing import List
from conclave.models import Client, Policy, AuditEvent, Consent, TrainingSession, ValidationCheck, GovernanceValidationResult, Organization, User, JoinRequest, Node, Notification
from conclave.server.storage import ClientRepository, PolicyRepository, AuditRepository, ConsentRepository, TrainingRepository, OrganizationRepository, UserRepository, JoinRequestRepository, NodeRepository, NotificationRepository

# Client Exceptions
class DuplicateClientError(Exception):
    pass

class ClientNotFoundError(Exception):
    pass

# Policy Exceptions
class DuplicatePolicyError(Exception):
    pass

class PolicyNotFoundError(Exception):
    pass

# Consent Exceptions
class DuplicateConsentError(Exception):
    pass

class ConsentNotFoundError(Exception):
    pass

# Training Exceptions
class DuplicateTrainingError(Exception):
    pass

class TrainingNotFoundError(Exception):
    pass

class TrainingValidationError(Exception):
    def __init__(self, message: str, validation_result: GovernanceValidationResult = None):
        super().__init__(message)
        self.validation_result = validation_result

# Audit Exceptions
class AuditNotFoundError(Exception):
    pass

# Organization Exceptions
class DuplicateOrganizationError(Exception):
    pass

class OrganizationNotFoundError(Exception):
    pass

# User Exceptions
class DuplicateUserError(Exception):
    pass

class UserNotFoundError(Exception):
    pass

# Auth Exceptions
class InvalidCredentialsError(Exception):
    pass

class InactiveUserError(Exception):
    pass

class AuthenticationError(Exception):
    pass

class JoinRequestNotFoundError(Exception):
    pass

class JoinRequestAlreadyExistsError(Exception):
    pass

class NodeNotFoundError(Exception):
    pass



# Audit Service
class AuditService:
    def __init__(self, repository: AuditRepository):
        self.repository = repository

    def log_event(self, event_type: str, resource_type: str, resource_name: str, action: str, status: str, message: str) -> AuditEvent:
        try:
            last_event = self.repository.find_last_event()
        except Exception:
            last_event = None

        prev_hash = last_event.hash if last_event else "0"

        event = AuditEvent(
            event_type=event_type,
            resource_type=resource_type,
            resource_name=resource_name,
            action=action,
            status=status,
            message=message,
            previous_hash=prev_hash
        )
        event.hash = event.calculate_hash(prev_hash)
        saved_event = self.repository.save(event)
        try:
            if event_type not in ("NOTIFICATION_READ", "NOTIFICATION_READ_ALL"):
                from conclave.server.registry import ServiceRegistry
                registry = ServiceRegistry()
                registry.notification_hub.trigger_event(
                    event_type=event_type,
                    resource_name=resource_name,
                    status=status,
                    message=message
                )
        except Exception as e:
            print(f"Error triggering notifications: {e}")
        return saved_event

    def verify_ledger(self) -> dict:
        """
        Verify the cryptographic integrity of the entire audit chain.
        Raises ValueError if any tampering or mismatch is detected.
        """
        from datetime import datetime
        events = self.repository.find_all()
        ordered_events = list(reversed(events))
        
        expected_prev_hash = "0"
        for idx, event in enumerate(ordered_events):
            if event.previous_hash != expected_prev_hash:
                raise ValueError(
                    f"Audit chain compromised: previous_hash mismatch at block {event.id} (timestamp: {event.timestamp}). "
                    f"Expected: {expected_prev_hash}, Found: {event.previous_hash}"
                )
            
            calculated = event.calculate_hash(event.previous_hash)
            if event.hash != calculated:
                raise ValueError(
                    f"Audit chain compromised: data tampering detected at block {event.id} (timestamp: {event.timestamp}). "
                    f"Recalculated hash does not match stored hash."
                )
            
            expected_prev_hash = event.hash

        return {
            "verified_blocks": len(events),
            "status": "Secure",
            "timestamp": datetime.now().isoformat()
        }

    def get_all_events(self) -> List[AuditEvent]:
        return self.repository.find_all()

    def get_event(self, event_id: str) -> AuditEvent:
        event = self.repository.find_by_id(event_id)
        if not event:
            raise AuditNotFoundError(f"Audit event with ID '{event_id}' not found.")
        return event

    def clear_logs(self):
        self.repository.clear()
        self.log_event(
            event_type="AUDIT_CLEARED",
            resource_type="Audit",
            resource_name="all",
            action="clear",
            status="Success",
            message="System audit logs cleared."
        )


# Client Service
class ClientService:
    def __init__(self, repository: ClientRepository, audit_service: AuditService):
        self.repository = repository
        self.audit_service = audit_service

    def register_client(self, name: str) -> Client:
        name_clean = name.strip()
        try:
            if not name_clean:
                raise ValueError("Client name cannot be empty.")
                
            if self.repository.find_by_name(name_clean):
                raise DuplicateClientError(f"Client '{name_clean}' already exists.")
                
            client = Client(name=name_clean)
            saved = self.repository.save(client)
            self.audit_service.log_event(
                event_type="CLIENT_REGISTRATION",
                resource_type="Client",
                resource_name=name_clean,
                action="register",
                status="Success",
                message=f"Client '{name_clean}' registered successfully."
            )
            return saved
        except Exception as e:
            self.audit_service.log_event(
                event_type="CLIENT_REGISTRATION",
                resource_type="Client",
                resource_name=name_clean or "unknown",
                action="register",
                status="Failure",
                message=str(e)
            )
            raise

    def list_clients(self) -> List[Client]:
        return self.repository.find_all()

    def get_client(self, name: str) -> Client:
        client = self.repository.find_by_name(name)
        if not client:
            raise ClientNotFoundError(f"Client '{name}' not found.")
        return client

    def remove_client(self, name: str) -> bool:
        name_clean = name.strip()
        try:
            client = self.get_client(name_clean)
            deleted = self.repository.delete_by_name(client.name)
            if deleted:
                self.audit_service.log_event(
                    event_type="CLIENT_REMOVAL",
                    resource_type="Client",
                    resource_name=client.name,
                    action="remove",
                    status="Success",
                    message=f"Client '{client.name}' removed successfully."
                )
            return deleted
        except Exception as e:
            self.audit_service.log_event(
                event_type="CLIENT_REMOVAL",
                resource_type="Client",
                resource_name=name_clean or "unknown",
                action="remove",
                status="Failure",
                message=str(e)
            )
            raise


# Policy Service
class PolicyService:
    def __init__(self, repository: PolicyRepository, audit_service: AuditService):
        self.repository = repository
        self.audit_service = audit_service

    def create_policy(self, name: str, description: str = "", secagg_enabled: bool = False, dp_enabled: bool = False, dp_epsilon: float = 1.0, dp_delta: float = 1e-5) -> Policy:
        name_clean = name.strip()
        try:
            if not name_clean:
                raise ValueError("Policy name cannot be empty.")
                
            if self.repository.find_by_name(name_clean):
                raise DuplicatePolicyError(f"Policy '{name_clean}' already exists.")
                
            policy = Policy(
                name=name_clean,
                description=description,
                status="Enabled",
                secagg_enabled=secagg_enabled,
                dp_enabled=dp_enabled,
                dp_epsilon=dp_epsilon,
                dp_delta=dp_delta
            )
            saved_policy = self.repository.save(policy)
            
            self.audit_service.log_event(
                event_type="POLICY_CREATION",
                resource_type="Policy",
                resource_name=saved_policy.name,
                action="create",
                status="Success",
                message=f"Policy '{saved_policy.name}' created with description: '{saved_policy.description}'"
            )
            return saved_policy
        except Exception as e:
            self.audit_service.log_event(
                event_type="POLICY_CREATION",
                resource_type="Policy",
                resource_name=name_clean or "unknown",
                action="create",
                status="Failure",
                message=str(e)
            )
            raise

    def list_policies(self) -> List[Policy]:
        return self.repository.find_all()

    def get_policy(self, name: str) -> Policy:
        policy = self.repository.find_by_name(name)
        if not policy:
            raise PolicyNotFoundError(f"Policy '{name}' not found.")
        return policy

    def enable_policy(self, name: str) -> Policy:
        name_clean = name.strip()
        try:
            policy = self.get_policy(name_clean)
            policy.status = "Enabled"
            saved = self.repository.save(policy)
            self.audit_service.log_event(
                event_type="POLICY_ENABLING",
                resource_type="Policy",
                resource_name=saved.name,
                action="enable",
                status="Success",
                message=f"Policy '{saved.name}' enabled."
            )
            return saved
        except Exception as e:
            self.audit_service.log_event(
                event_type="POLICY_ENABLING",
                resource_type="Policy",
                resource_name=name_clean or "unknown",
                action="enable",
                status="Failure",
                message=str(e)
            )
            raise

    def disable_policy(self, name: str) -> Policy:
        name_clean = name.strip()
        try:
            policy = self.get_policy(name_clean)
            policy.status = "Disabled"
            saved = self.repository.save(policy)
            self.audit_service.log_event(
                event_type="POLICY_DISABLING",
                resource_type="Policy",
                resource_name=saved.name,
                action="disable",
                status="Success",
                message=f"Policy '{saved.name}' disabled."
            )
            return saved
        except Exception as e:
            self.audit_service.log_event(
                event_type="POLICY_DISABLING",
                resource_type="Policy",
                resource_name=name_clean or "unknown",
                action="disable",
                status="Failure",
                message=str(e)
            )
            raise

    def remove_policy(self, name: str) -> bool:
        name_clean = name.strip()
        try:
            policy = self.get_policy(name_clean)
            deleted = self.repository.delete_by_name(policy.name)
            if deleted:
                self.audit_service.log_event(
                    event_type="POLICY_REMOVAL",
                    resource_type="Policy",
                    resource_name=policy.name,
                    action="remove",
                    status="Success",
                    message=f"Policy '{policy.name}' removed."
                )
            return deleted
        except Exception as e:
            self.audit_service.log_event(
                event_type="POLICY_REMOVAL",
                resource_type="Policy",
                resource_name=name_clean or "unknown",
                action="remove",
                status="Failure",
                message=str(e)
            )
            raise


# Consent Service
class ConsentService:
    def __init__(self, repository: ConsentRepository, client_service: ClientService, audit_service: AuditService):
        self.repository = repository
        self.client_service = client_service
        self.audit_service = audit_service

    def grant_consent(self, client_name: str, dataset_name: str) -> Consent:
        client_name_clean = client_name.strip()
        dataset_clean = dataset_name.strip()
        try:
            if not dataset_clean:
                raise ValueError("Dataset name cannot be empty.")
                
            client = self.client_service.get_client(client_name_clean)
            
            existing = self.repository.find_by_client_and_dataset(client.id, dataset_clean)
            if existing and existing.status == "Granted":
                raise DuplicateConsentError(f"Active consent for client '{client.name}' and dataset '{dataset_clean}' already exists.")
                
            from datetime import datetime
            if existing:
                existing.status = "Granted"
                existing.granted_at = datetime.now()
                existing.revoked_at = None
                consent = self.repository.save(existing)
            else:
                consent = Consent(client_id=client.id, dataset_name=dataset_clean, status="Granted")
                consent = self.repository.save(consent)
                
            self.audit_service.log_event(
                event_type="CONSENT_GRANT",
                resource_type="Consent",
                resource_name=f"{client.name}:{dataset_clean}",
                action="grant",
                status="Success",
                message=f"Consent granted for client '{client.name}' to use dataset '{dataset_clean}'."
            )
            return consent
        except Exception as e:
            self.audit_service.log_event(
                event_type="CONSENT_GRANT",
                resource_type="Consent",
                resource_name=f"{client_name_clean}:{dataset_clean or 'unknown'}",
                action="grant",
                status="Failure",
                message=str(e)
            )
            raise

    def revoke_consent(self, client_name: str, dataset_name: str) -> Consent:
        client_name_clean = client_name.strip()
        dataset_clean = dataset_name.strip()
        try:
            client = self.client_service.get_client(client_name_clean)
            
            consent = self.repository.find_by_client_and_dataset(client.id, dataset_clean)
            if not consent or consent.status == "Revoked":
                raise ConsentNotFoundError(f"No active consent found for client '{client.name}' and dataset '{dataset_clean}'.")
                
            from datetime import datetime
            consent.status = "Revoked"
            consent.revoked_at = datetime.now()
            saved = self.repository.save(consent)
            
            self.audit_service.log_event(
                event_type="CONSENT_REVOCATION",
                resource_type="Consent",
                resource_name=f"{client.name}:{dataset_clean}",
                action="revoke",
                status="Success",
                message=f"Consent revoked for client '{client.name}' on dataset '{dataset_clean}'."
            )
            return saved
        except Exception as e:
            self.audit_service.log_event(
                event_type="CONSENT_REVOCATION",
                resource_type="Consent",
                resource_name=f"{client_name_clean}:{dataset_clean or 'unknown'}",
                action="revoke",
                status="Failure",
                message=str(e)
            )
            raise

    def list_consents(self) -> List[Consent]:
        return self.repository.find_all()

    def get_consents_for_client(self, client_name: str) -> List[Consent]:
        client = self.client_service.get_client(client_name)
        return self.repository.find_by_client(client.id)


# Governance Service & Rules Pipeline
class GovernanceRule:
    def name(self) -> str:
        raise NotImplementedError
    def validate(self, context) -> ValidationCheck:
        raise NotImplementedError

class ClientsValidationRule(GovernanceRule):
    def name(self) -> str:
        return "Clients Verified"

    def validate(self, context) -> ValidationCheck:
        session = context.session
        client_service = context.client_service
        
        errors = []
        for client_name in session.participating_clients:
            try:
                client = client_service.get_client(client_name)
                if client.status != "Active":
                    errors.append(f"Client '{client_name}' is not active.")
            except Exception:
                errors.append(f"Client '{client_name}' not found.")
                
        if errors:
            return ValidationCheck(self.name(), passed=False, message="; ".join(errors))
        return ValidationCheck(self.name(), passed=True, message="All participating clients exist and are active.")

class PolicyValidationRule(GovernanceRule):
    def name(self) -> str:
        return "Policy Verified"

    def validate(self, context) -> ValidationCheck:
        session = context.session
        policy_service = context.policy_service
        
        try:
            policy = policy_service.get_policy(session.assigned_policy)
            if policy.status != "Enabled":
                return ValidationCheck(self.name(), passed=False, message=f"Policy '{session.assigned_policy}' is disabled.")
            return ValidationCheck(self.name(), passed=True, message=f"Policy '{session.assigned_policy}' is active.")
        except Exception:
            return ValidationCheck(self.name(), passed=False, message=f"Policy '{session.assigned_policy}' not found.")

class ConsentValidationRule(GovernanceRule):
    def name(self) -> str:
        return "Consent Verified"

    def validate(self, context) -> ValidationCheck:
        session = context.session
        consent_service = context.consent_service
        client_service = context.client_service
        
        errors = []
        for client_name in session.participating_clients:
            try:
                client = client_service.get_client(client_name)
                consents = consent_service.get_consents_for_client(client_name)
                has_consent = any(c.dataset_name.lower() == session.dataset_name.lower() and c.status == "Granted" for c in consents)
                if not has_consent:
                    errors.append(f"Consent not granted for client '{client_name}' on dataset '{session.dataset_name}'.")
            except Exception:
                errors.append(f"Cannot verify consent for non-existent client '{client_name}'.")
                
        if errors:
            return ValidationCheck(self.name(), passed=False, message="; ".join(errors))
        return ValidationCheck(self.name(), passed=True, message="All clients have granted active consent.")

class PrivacyValidationRule(GovernanceRule):
    def name(self) -> str:
        return "Privacy-Preserving Verification"

    def validate(self, context) -> ValidationCheck:
        session = context.session
        policy_service = context.policy_service
        
        try:
            policy = policy_service.get_policy(session.assigned_policy)
        except Exception:
            return ValidationCheck(self.name(), passed=False, message=f"Policy '{session.assigned_policy}' not found.")

        errors = []
        if policy.secagg_enabled:
            if len(session.participating_clients) < 3:
                errors.append(f"Secure Aggregation requires at least 3 participating clients (currently: {len(session.participating_clients)}).")
        
        if policy.dp_enabled:
            if policy.dp_epsilon <= 0:
                errors.append(f"Differential Privacy epsilon budget must be greater than 0 (currently: {policy.dp_epsilon}).")

        if errors:
            return ValidationCheck(self.name(), passed=False, message="; ".join(errors))
        
        details = []
        if policy.secagg_enabled:
            details.append("SecAgg Enabled (Google pairwise masking protocol)")
        if policy.dp_enabled:
            details.append(f"Differential Privacy Enabled (Epsilon={policy.dp_epsilon}, Delta={policy.dp_delta})")
        if not details:
            details.append("No privacy restrictions configured.")
            
        return ValidationCheck(self.name(), passed=True, message="; ".join(details))

class GovernanceContext:
    def __init__(self, session: TrainingSession, client_service: ClientService, policy_service: PolicyService, consent_service: ConsentService):
        self.session = session
        self.client_service = client_service
        self.policy_service = policy_service
        self.consent_service = consent_service

class GovernanceService:
    def __init__(self, client_service: ClientService, policy_service: PolicyService, consent_service: ConsentService):
        self.client_service = client_service
        self.policy_service = policy_service
        self.consent_service = consent_service
        self._rules = []
        self._register_default_rules()

    def _register_default_rules(self):
        self._rules.append(ClientsValidationRule())
        self._rules.append(PolicyValidationRule())
        self._rules.append(ConsentValidationRule())
        self._rules.append(PrivacyValidationRule())

    def register_rule(self, rule: GovernanceRule):
        self._rules.append(rule)

    def validate(self, session: TrainingSession) -> GovernanceValidationResult:
        context = GovernanceContext(
            session=session,
            client_service=self.client_service,
            policy_service=self.policy_service,
            consent_service=self.consent_service
        )
        checks = []
        passed = True
        for rule in self._rules:
            check = rule.validate(context)
            checks.append(check)
            if not check.passed:
                passed = False
        return GovernanceValidationResult(passed=passed, checks=checks)


# Training Service
class TrainingService:
    def __init__(self, repository: TrainingRepository, governance_service: GovernanceService, orchestrator, audit_service: AuditService):
        self.repository = repository
        self.governance_service = governance_service
        self.orchestrator = orchestrator
        self.audit_service = audit_service

    def create_session(self, name: str, client_names: List[str], policy_name: str, dataset_name: str, description: str = "", priority: str = "Medium") -> TrainingSession:
        name_clean = name.strip()
        try:
            if not name_clean:
                raise ValueError("Training session name cannot be empty.")
            if not client_names:
                raise ValueError("Training session must have at least one participating client.")
            if not policy_name.strip():
                raise ValueError("Policy name cannot be empty.")
            if not dataset_name.strip():
                raise ValueError("Dataset name cannot be empty.")
                
            if self.repository.find_by_name(name_clean):
                raise DuplicateTrainingError(f"Training session '{name_clean}' already exists.")
                
            session = TrainingSession(
                name=name_clean,
                participating_clients=client_names,
                assigned_policy=policy_name,
                dataset_name=dataset_name,
                description=description,
                priority=priority
            )
            saved = self.repository.save(session)
            
            self.audit_service.log_event(
                event_type="TRAINING_CREATION",
                resource_type="Training",
                resource_name=saved.name,
                action="create",
                status="Success",
                message=f"Training session '{saved.name}' created with policy '{saved.assigned_policy}' and dataset '{saved.dataset_name}'."
            )
            return saved
        except Exception as e:
            self.audit_service.log_event(
                event_type="TRAINING_CREATION",
                resource_type="Training",
                resource_name=name_clean or "unknown",
                action="create",
                status="Failure",
                message=str(e)
            )
            raise

    def list_sessions(self) -> List[TrainingSession]:
        return self.repository.find_all()

    def get_session(self, name: str) -> TrainingSession:
        session = self.repository.find_by_name(name)
        if not session:
            raise TrainingNotFoundError(f"Training session '{name}' not found.")
        return session

    def start_session(self, name: str) -> tuple:
        name_clean = name.strip()
        try:
            session = self.get_session(name_clean)
            
            # Delegate execution lifecycle and pre-checks to the TrainingOrchestrator
            self.orchestrator.run_session(session)
            
            validation_result = self.governance_service.validate(session)
            return (session, validation_result)
        except Exception as e:
            val_result = getattr(e, "validation_result", None)
            if not val_result:
                try:
                    val_result = self.governance_service.validate(session)
                except Exception:
                    pass
            raise TrainingValidationError(str(e), validation_result=val_result)

    def stop_session(self, name: str) -> TrainingSession:
        name_clean = name.strip()
        try:
            session = self.get_session(name_clean)
            session.status = "Stopped"
            from datetime import datetime
            session.completed_at = datetime.now()
            saved = self.repository.save(session)
            
            self.audit_service.log_event(
                event_type="TRAINING_STOP",
                resource_type="Training",
                resource_name=saved.name,
                action="stop",
                status="Success",
                message=f"Training session '{saved.name}' stopped."
            )
            return saved
        except Exception as e:
            self.audit_service.log_event(
                event_type="TRAINING_STOP",
                resource_type="Training",
                resource_name=name_clean or "unknown",
                action="stop",
                status="Failure",
                message=str(e)
            )
            raise

    def remove_session(self, name: str) -> bool:
        name_clean = name.strip()
        try:
            session = self.get_session(name_clean)
            deleted = self.repository.delete_by_name(session.name)
            if deleted:
                self.audit_service.log_event(
                    event_type="TRAINING_REMOVAL",
                    resource_type="Training",
                    resource_name=session.name,
                    action="remove",
                    status="Success",
                    message=f"Training session '{session.name}' removed."
                )
            return deleted
        except Exception as e:
            self.audit_service.log_event(
                event_type="TRAINING_REMOVAL",
                resource_type="Training",
                resource_name=name_clean or "unknown",
                action="remove",
                status="Failure",
                message=str(e)
            )
            raise

class OrganizationService:
    def __init__(self, repository: OrganizationRepository, audit_service: AuditService):
        self.repository = repository
        self.audit_service = audit_service

    def create_organization(self, name: str, organization_type: str, description: str = "") -> Organization:
        if not name.strip() or not organization_type.strip():
            raise ValueError("Organization name and type cannot be empty.")
            
        existing = self.repository.find_by_name(name)
        if existing:
            self.audit_service.log_event(
                event_type="ORGANIZATION_CREATION_FAILED",
                resource_type="Organization",
                resource_name=name,
                action="create",
                status="Failure",
                message=f"Organization '{name}' already exists."
            )
            raise DuplicateOrganizationError(f"Organization '{name}' already exists.")

        org = Organization(name=name, organization_type=organization_type, description=description)
        saved = self.repository.save(org)

        self.audit_service.log_event(
            event_type="ORGANIZATION_CREATION",
            resource_type="Organization",
            resource_name=saved.name,
            action="create",
            status="Success",
            message=f"Organization '{saved.name}' registered successfully with type '{saved.organization_type}'."
        )
        return saved

    def list_organizations(self) -> List[Organization]:
        return self.repository.find_all()

    def get_organization(self, name: str) -> Organization:
        org = self.repository.find_by_name(name)
        if not org:
            raise OrganizationNotFoundError(f"Organization '{name}' not found.")
        return org

    def update_organization(self, name: str, organization_type: str = None, description: str = None) -> Organization:
        org = self.repository.find_by_name(name)
        if not org:
            self.audit_service.log_event(
                event_type="ORGANIZATION_UPDATE_FAILED",
                resource_type="Organization",
                resource_name=name,
                action="update",
                status="Failure",
                message=f"Organization '{name}' not found for update."
            )
            raise OrganizationNotFoundError(f"Organization '{name}' not found.")

        if organization_type is not None:
            if not organization_type.strip():
                raise ValueError("Organization type cannot be empty.")
            org.organization_type = organization_type.strip()
            
        if description is not None:
            org.description = description.strip()

        from datetime import datetime
        org.updated_at = datetime.now()
        saved = self.repository.save(org)

        self.audit_service.log_event(
            event_type="ORGANIZATION_UPDATE",
            resource_type="Organization",
            resource_name=saved.name,
            action="update",
            status="Success",
            message=f"Organization '{saved.name}' details updated successfully."
        )
        return saved

    def deactivate_organization(self, name: str) -> Organization:
        org = self.repository.find_by_name(name)
        if not org:
            self.audit_service.log_event(
                event_type="ORGANIZATION_DEACTIVATION_FAILED",
                resource_type="Organization",
                resource_name=name,
                action="deactivate",
                status="Failure",
                message=f"Organization '{name}' not found for deactivation."
            )
            raise OrganizationNotFoundError(f"Organization '{name}' not found.")

        org.status = "Inactive"
        from datetime import datetime
        org.updated_at = datetime.now()
        saved = self.repository.save(org)

        self.audit_service.log_event(
            event_type="ORGANIZATION_DEACTIVATION",
            resource_type="Organization",
            resource_name=saved.name,
            action="deactivate",
            status="Success",
            message=f"Organization '{saved.name}' deactivated successfully."
        )
        return saved

    def remove_organization(self, name: str) -> bool:
        org = self.repository.find_by_name(name)
        if not org:
            self.audit_service.log_event(
                event_type="ORGANIZATION_REMOVAL_FAILED",
                resource_type="Organization",
                resource_name=name,
                action="remove",
                status="Failure",
                message=f"Organization '{name}' not found for removal."
            )
            raise OrganizationNotFoundError(f"Organization '{name}' not found.")

        success = self.repository.delete_by_name(name)
        if success:
            self.audit_service.log_event(
                event_type="ORGANIZATION_REMOVAL",
                resource_type="Organization",
                resource_name=name,
                action="remove",
                status="Success",
                message=f"Organization '{name}' removed successfully."
            )
        return success

class UserService:
    def __init__(self, repository: UserRepository, org_repository: OrganizationRepository, audit_service: AuditService):
        self.repository = repository
        self.org_repository = org_repository
        self.audit_service = audit_service

    def create_user(self, username: str, org_name: str, email: str, full_name: str, password: str = None, role: str = "Operator") -> User:
        username = username.strip()
        org_name = org_name.strip()
        email = email.strip()
        full_name = full_name.strip()

        if not username or not org_name or not email or not full_name:
            raise ValueError("All fields (username, org, email, name) are required.")

        # 1. Validate organization exists
        org = self.org_repository.find_by_name(org_name)
        if not org:
            self.audit_service.log_event(
                event_type="USER_CREATION_FAILED",
                resource_type="User",
                resource_name=username,
                action="create",
                status="Failure",
                message=f"Organization '{org_name}' not found for user."
            )
            raise OrganizationNotFoundError(f"Organization '{org_name}' not found.")

        # 2. Check username duplicate
        if self.repository.find_by_username(username):
            self.audit_service.log_event(
                event_type="USER_CREATION_FAILED",
                resource_type="User",
                resource_name=username,
                action="create",
                status="Failure",
                message=f"Username '{username}' already exists."
            )
            raise DuplicateUserError(f"Username '{username}' already exists.")

        # 3. Check email duplicate
        if self.repository.find_by_email(email):
            self.audit_service.log_event(
                event_type="USER_CREATION_FAILED",
                resource_type="User",
                resource_name=username,
                action="create",
                status="Failure",
                message=f"User email '{email}' already exists."
            )
            raise DuplicateUserError(f"User email '{email}' already exists.")

        password_hash = None
        if password:
            from conclave.server.security import hash_password
            password_hash = hash_password(password)

        from conclave.server.authz import VALID_ROLES
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}.")

        user = User(
            organization_id=org.id,
            username=username,
            email=email,
            full_name=full_name,
            role=role,
            password_hash=password_hash
        )
        saved = self.repository.save(user)

        self.audit_service.log_event(
            event_type="USER_CREATION",
            resource_type="User",
            resource_name=saved.username,
            action="create",
            status="Success",
            message=f"User '{saved.username}' registered successfully under organization '{org.name}'."
        )
        return saved

    def list_users(self) -> List[User]:
        return self.repository.find_all()

    def get_user(self, username: str) -> User:
        user = self.repository.find_by_username(username)
        if not user:
            raise UserNotFoundError(f"User '{username}' not found.")
        return user

    def update_user(self, username: str, email: str = None, full_name: str = None) -> User:
        user = self.repository.find_by_username(username)
        if not user:
            self.audit_service.log_event(
                event_type="USER_UPDATE_FAILED",
                resource_type="User",
                resource_name=username,
                action="update",
                status="Failure",
                message=f"User '{username}' not found for update."
            )
            raise UserNotFoundError(f"User '{username}' not found.")

        if email is not None:
            email = email.strip()
            if not email:
                raise ValueError("Email cannot be empty.")
            # check email duplicate
            existing = self.repository.find_by_email(email)
            if existing and existing.id != user.id:
                self.audit_service.log_event(
                    event_type="USER_UPDATE_FAILED",
                    resource_type="User",
                    resource_name=username,
                    action="update",
                    status="Failure",
                    message=f"User email '{email}' already exists."
                )
                raise DuplicateUserError(f"User email '{email}' already exists.")
            user.email = email

        if full_name is not None:
            full_name = full_name.strip()
            if not full_name:
                raise ValueError("Full name cannot be empty.")
            user.full_name = full_name

        from datetime import datetime
        user.updated_at = datetime.now()
        saved = self.repository.save(user)

        self.audit_service.log_event(
            event_type="USER_UPDATE",
            resource_type="User",
            resource_name=saved.username,
            action="update",
            status="Success",
            message=f"User '{saved.username}' details updated successfully."
        )
        return saved

    def deactivate_user(self, username: str) -> User:
        user = self.repository.find_by_username(username)
        if not user:
            self.audit_service.log_event(
                event_type="USER_DEACTIVATION_FAILED",
                resource_type="User",
                resource_name=username,
                action="deactivate",
                status="Failure",
                message=f"User '{username}' not found for deactivation."
            )
            raise UserNotFoundError(f"User '{username}' not found.")

        user.status = "Inactive"
        from datetime import datetime
        user.updated_at = datetime.now()
        saved = self.repository.save(user)

        self.audit_service.log_event(
            event_type="USER_DEACTIVATION",
            resource_type="User",
            resource_name=saved.username,
            action="deactivate",
            status="Success",
            message=f"User '{saved.username}' deactivated successfully."
        )
        return saved

    def remove_user(self, username: str) -> bool:
        user = self.repository.find_by_username(username)
        if not user:
            self.audit_service.log_event(
                event_type="USER_REMOVAL_FAILED",
                resource_type="User",
                resource_name=username,
                action="remove",
                status="Failure",
                message=f"User '{username}' not found for removal."
            )
            raise UserNotFoundError(f"User '{username}' not found.")

        success = self.repository.delete_by_username(username)
        if success:
            self.audit_service.log_event(
                event_type="USER_REMOVAL",
                resource_type="User",
                resource_name=username,
                action="remove",
                status="Success",
                message=f"User '{username}' removed successfully."
            )
        return success

class AuthService:
    def __init__(self, user_service: UserService, audit_service: AuditService):
        self.user_service = user_service
        self.audit_service = audit_service

    def register(self, username: str, org_name: str, email: str, full_name: str, password: str, role: str = "Operator") -> User:
        try:
            user = self.user_service.create_user(
                username=username,
                org_name=org_name,
                email=email,
                full_name=full_name,
                password=password,
                role=role
            )
            return user
        except Exception as e:
            raise e

    def login(self, username_or_email: str, password: str) -> str:
        user = None
        u = self.user_service.repository.find_by_username(username_or_email)
        if u:
            user = u
        else:
            u = self.user_service.repository.find_by_email(username_or_email)
            if u:
                user = u

        if not user:
            self.audit_service.log_event(
                event_type="USER_LOGIN_FAILED",
                resource_type="User",
                resource_name=username_or_email,
                action="login",
                status="Failure",
                message="Invalid username or email."
            )
            raise InvalidCredentialsError("Invalid credentials.")

        if user.status != "Active":
            self.audit_service.log_event(
                event_type="USER_LOGIN_FAILED",
                resource_type="User",
                resource_name=user.username,
                action="login",
                status="Failure",
                message=f"User '{user.username}' is inactive."
            )
            raise InactiveUserError("User account is inactive. Please contact your organization administrator.")

        from conclave.server.security import verify_password, create_access_token
        if not user.password_hash or not verify_password(password, user.password_hash):
            self.audit_service.log_event(
                event_type="USER_LOGIN_FAILED",
                resource_type="User",
                resource_name=user.username,
                action="login",
                status="Failure",
                message="Incorrect password."
            )
            raise InvalidCredentialsError("Invalid credentials.")

        from datetime import datetime
        user.last_login = datetime.now()
        self.user_service.repository.save(user)

        token = create_access_token({
            "sub": user.username,
            "role": getattr(user, 'role', 'Operator'),
            "organization_id": user.organization_id,
        })

        self.audit_service.log_event(
            event_type="USER_LOGIN",
            resource_type="User",
            resource_name=user.username,
            action="login",
            status="Success",
            message=f"User '{user.username}' logged in successfully."
        )
        return token


class OnboardingService:
    """
    Handles the three first-time setup scenarios:
      1. Create a new organization (caller becomes Org Admin)
      2. Request to join an existing organization (creates a JoinRequest)
      3. Approve / reject a pending JoinRequest (performed by Org Admin)
    """

    def __init__(
        self,
        org_service: OrganizationService,
        user_service: UserService,
        auth_service: AuthService,
        join_request_repository: JoinRequestRepository,
        audit_service: AuditService,
    ):
        self.org_service = org_service
        self.user_service = user_service
        self.auth_service = auth_service
        self.join_request_repository = join_request_repository
        self.audit_service = audit_service

    def get_status(self) -> dict:
        """Return whether the server has any organizations (i.e., is initialized)."""
        orgs = self.org_service.list_organizations()
        return {
            "initialized": len(orgs) > 0,
            "org_count": len(orgs),
        }

    def create_with_org(
        self,
        org_name: str,
        org_type: str,
        username: str,
        email: str,
        full_name: str,
        password: str,
        description: str = "",
    ) -> tuple:
        """
        Scenario 1: Create a brand-new organization and its first admin user.
        Returns (organization, user, token).
        Raises ValueError if the server is already initialized.
        """
        status = self.get_status()
        if status["initialized"]:
            raise ValueError(
                "This Conclave server is already set up. "
                "Contact your System Admin to create additional organizations."
            )

        # Create the organization
        org = self.org_service.create_organization(
            name=org_name,
            organization_type=org_type,
            description=description,
        )

        # Hash password
        from conclave.server.security import hash_password, create_access_token
        password_hash = hash_password(password)

        # Create the admin user directly (bypasses org lookup by name; we already have the org)
        from datetime import datetime
        user = User(
            organization_id=org.id,
            username=username,
            email=email,
            full_name=full_name,
            status="Active",
            role="Organization Admin",
            password_hash=password_hash,
        )
        self.user_service.repository.save(user)

        self.audit_service.log_event(
            event_type="ONBOARDING_CREATE",
            resource_type="Organization",
            resource_name=org.name,
            action="create_with_admin",
            status="Success",
            message=f"Organization '{org.name}' created with admin user '{username}'.",
        )

        # Issue JWT
        token = create_access_token({
            "sub": user.username,
            "role": user.role,
            "organization_id": user.organization_id,
        })

        return org, user, token

    def request_join(
        self,
        org_id: str,
        username: str,
        email: str,
        full_name: str,
        password: str,
    ) -> JoinRequest:
        """
        Scenario 2: Submit a join request for an existing organization.
        Returns the JoinRequest (with invite_code visible once).
        """
        # Validate org exists
        org = self.org_service.repository.find_by_name(org_id)
        if not org:
            # Try by id prefix or exact id
            raise OrganizationNotFoundError(f"Organization '{org_id}' not found.")

        # Check no duplicate username / email in join requests
        existing = self.join_request_repository.find_by_username(username)
        if existing and existing.status == "Pending":
            raise JoinRequestAlreadyExistsError(
                f"A pending join request for username '{username}' already exists."
            )

        # Check user doesn't already exist
        existing_user = self.user_service.repository.find_by_username(username)
        if existing_user:
            raise DuplicateUserError(f"Username '{username}' is already taken.")

        from conclave.server.security import hash_password
        password_hash = hash_password(password)

        req = JoinRequest(
            org_id=org.id,
            username=username,
            email=email,
            full_name=full_name,
            password_hash=password_hash,
        )
        self.join_request_repository.save(req)

        self.audit_service.log_event(
            event_type="JOIN_REQUEST_SUBMITTED",
            resource_type="JoinRequest",
            resource_name=username,
            action="join",
            status="Pending",
            message=f"User '{username}' requested to join organization '{org.name}'.",
        )
        return req

    def approve_join(self, request_id: str, reviewed_by: str) -> User:
        """
        Approve a pending JoinRequest and create the user as an Operator.
        Returns the new User.
        """
        req = self.join_request_repository.find_by_id(request_id)
        if not req:
            raise JoinRequestNotFoundError(f"Join request '{request_id}' not found.")
        if req.status != "Pending":
            raise ValueError(f"Join request is already '{req.status}'.")

        from datetime import datetime
        user = User(
            organization_id=req.org_id,
            username=req.username,
            email=req.email,
            full_name=req.full_name,
            status="Active",
            role="Operator",
            password_hash=req.password_hash,
        )
        self.user_service.repository.save(user)

        req.status = "Approved"
        req.reviewed_by = reviewed_by
        req.reviewed_at = datetime.now()
        self.join_request_repository.save(req)

        self.audit_service.log_event(
            event_type="JOIN_REQUEST_APPROVED",
            resource_type="JoinRequest",
            resource_name=req.username,
            action="approve",
            status="Success",
            message=f"Join request for '{req.username}' approved by '{reviewed_by}'.",
        )
        return user

    def reject_join(self, request_id: str, reviewed_by: str) -> JoinRequest:
        """Reject a pending JoinRequest."""
        req = self.join_request_repository.find_by_id(request_id)
        if not req:
            raise JoinRequestNotFoundError(f"Join request '{request_id}' not found.")
        if req.status != "Pending":
            raise ValueError(f"Join request is already '{req.status}'.")

        from datetime import datetime
        req.status = "Rejected"
        req.reviewed_by = reviewed_by
        req.reviewed_at = datetime.now()
        self.join_request_repository.save(req)

        self.audit_service.log_event(
            event_type="JOIN_REQUEST_REJECTED",
            resource_type="JoinRequest",
            resource_name=req.username,
            action="reject",
            status="Success",
            message=f"Join request for '{req.username}' rejected by '{reviewed_by}'.",
        )
        return req

    def list_pending_requests(self, org_id: str) -> List[JoinRequest]:
        """Return all Pending join requests for a given organization."""
        return self.join_request_repository.find_pending_by_org(org_id)


def _generate_node_cert(node_id: str, public_key_pem: str) -> str:
    from conclave.server.pki import sign_node_cert
    return sign_node_cert(node_id, public_key_pem)


class NodeService:
    def __init__(self, node_repository: NodeRepository, audit_service: AuditService):
        self.node_repository = node_repository
        self.audit_service = audit_service

    def _transition_if_offline(self, node: Node) -> Node:
        """
        Dynamically transition node to 'Offline' if its last heartbeat was over 120 seconds ago.
        Only Online/Approved/Offline nodes are updated. Pending/Rejected/Revoked stay as-is.
        """
        from datetime import datetime
        if node.status in ("Approved", "Online", "Offline"):
            delta = (datetime.now() - node.last_heartbeat).total_seconds()
            if delta > 120.0:
                if node.status != "Offline":
                    node.status = "Offline"
                    self.node_repository.save(node)
        return node

    def register_node(self, organization_id: str, hostname: str, public_key: str, node_name: str = None,
                      os_name: str = "", os_version: str = "", architecture: str = "",
                      cpu_model: str = "", cpu_cores: int = 0, ram_gb: float = 0.0,
                      gpu_available: str = "No", gpu_vendor: str = "", gpu_model: str = "",
                      gpu_count: int = 0, gpu_vram: float = 0.0, cuda_version: str = "",
                      python_version: str = "", flower_version: str = "", conclave_version: str = "",
                      last_ip: str = "127.0.0.1") -> Node:
        
        import uuid
        node_id = str(uuid.uuid4())

        # Generate X.509 cert
        try:
            cert_pem = _generate_node_cert(node_id, public_key)
        except Exception as e:
            raise ValueError(f"Failed to generate certificate: {e}")

        registration_token = str(uuid.uuid4())

        node = Node(
            node_id=node_id,
            organization_id=organization_id,
            hostname=hostname,
            node_name=node_name,
            os_name=os_name,
            os_version=os_version,
            architecture=architecture,
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            ram_gb=ram_gb,
            gpu_available=gpu_available,
            gpu_vendor=gpu_vendor,
            gpu_model=gpu_model,
            gpu_count=gpu_count,
            gpu_vram=gpu_vram,
            cuda_version=cuda_version,
            python_version=python_version,
            flower_version=flower_version,
            conclave_version=conclave_version,
            status="Pending",
            last_ip=last_ip,
            public_key=public_key,
            certificate=cert_pem,
            registration_token=registration_token,
            trust_status="Untrusted"
        )
        saved = self.node_repository.save(node)

        self.audit_service.log_event(
            event_type="NODE_REGISTRATION",
            resource_type="Node",
            resource_name=saved.hostname,
            action="register",
            status="Success",
            message=f"Node '{saved.id}' registered for organization '{organization_id}' with certificate (status: Pending)."
        )
        return saved

    def list_nodes(self, org_id: str = None) -> List[Node]:
        """List all nodes. If org_id is provided, filter nodes to that org."""
        if org_id:
            nodes = self.node_repository.find_by_org(org_id)
        else:
            nodes = self.node_repository.find_all()
        # Apply offline state transitions
        for n in nodes:
            self._transition_if_offline(n)
        return nodes

    def get_node(self, node_id: str) -> Node:
        node = self.node_repository.find_by_id(node_id)
        if not node:
            raise NodeNotFoundError(f"Node '{node_id}' not found.")
        return self._transition_if_offline(node)

    def approve_node(self, node_id: str, reviewer: str) -> Node:
        node = self.get_node(node_id)
        if node.status == "Revoked":
            raise ValueError("Cannot approve a revoked node.")
        node.status = "Approved"
        node.trust_status = "Trusted"
        saved = self.node_repository.save(node)

        self.audit_service.log_event(
            event_type="NODE_APPROVAL",
            resource_type="Node",
            resource_name=saved.hostname,
            action="approve",
            status="Success",
            message=f"Node '{node_id}' approved and trusted by reviewer '{reviewer}'."
        )
        return saved

    def reject_node(self, node_id: str, reviewer: str) -> Node:
        node = self.get_node(node_id)
        node.status = "Rejected"
        node.trust_status = "Revoked"
        saved = self.node_repository.save(node)

        self.audit_service.log_event(
            event_type="NODE_REJECTION",
            resource_type="Node",
            resource_name=saved.hostname,
            action="reject",
            status="Success",
            message=f"Node '{node_id}' rejected by reviewer '{reviewer}'."
        )
        return saved

    def revoke_node(self, node_id: str, reviewer: str) -> Node:
        node = self.get_node(node_id)
        node.status = "Revoked"
        node.trust_status = "Revoked"
        saved = self.node_repository.save(node)

        self.audit_service.log_event(
            event_type="NODE_REVOCATION",
            resource_type="Node",
            resource_name=saved.hostname,
            action="revoke",
            status="Success",
            message=f"Node '{node_id}' revoked by reviewer '{reviewer}'."
        )
        return saved

    def heartbeat(self, node_id: str, ip_address: str) -> Node:
        node = self.node_repository.find_by_id(node_id)
        if not node:
            raise NodeNotFoundError(f"Node '{node_id}' not found.")

        # Heartbeat check
        if node.status not in ("Approved", "Online", "Offline"):
            raise ValueError(f"Heartbeat rejected: Node is not approved. Status is '{node.status}'.")
        if node.trust_status != "Trusted":
            raise ValueError(f"Heartbeat rejected: Node identity is untrusted/revoked. Trust status: '{node.trust_status}'.")

        from datetime import datetime
        node.last_heartbeat = datetime.now()
        node.last_ip = ip_address
        node.status = "Online"

        saved = self.node_repository.save(node)
        return saved


class NotificationService:
    def __init__(self, repository: NotificationRepository, audit_service: AuditService):
        self.repository = repository
        self.audit_service = audit_service

    def get_notifications(self) -> List[Notification]:
        return self.repository.find_all()

    def get_unread_notifications(self) -> List[Notification]:
        return self.repository.find_unread()

    def mark_as_read(self, notification_id: str) -> bool:
        success = self.repository.mark_as_read(notification_id)
        if success:
            self.audit_service.log_event(
                event_type="NOTIFICATION_READ",
                resource_type="Notification",
                resource_name=notification_id,
                action="read",
                status="Success",
                message=f"Notification '{notification_id}' marked as read."
            )
        return success

    def mark_all_read(self) -> int:
        count = self.repository.mark_all_read()
        if count > 0:
            self.audit_service.log_event(
                event_type="NOTIFICATION_READ_ALL",
                resource_type="Notification",
                resource_name="all",
                action="read_all",
                status="Success",
                message=f"Marked {count} notifications as read."
            )
        return count


