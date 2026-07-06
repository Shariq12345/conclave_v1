import os
from datetime import datetime

class ComplianceService:
    def __init__(self, registry):
        self.registry = registry

    def audit_hipaa(self) -> dict:
        """
        Runs security audit checks matching HIPAA Security Rule standards:
        - § 164.308(a)(4): Access Authorization (MFA for Administrators)
        - § 164.312(a)(1): Access Control (mTLS Node identity check)
        - § 164.312(e)(1): Transmission Security (Secure Aggregation active on policies)
        - § 164.312(b): Audit Controls (Active governance audit trail logs)
        """
        # 1. MFA Check for Admins
        try:
            users = self.registry.user_service.list_users()
            admins = [u for u in users if u.role in ("System Admin", "Organization Admin")]
            mfa_passed = True
            mfa_details = []
            
            if not admins:
                mfa_passed = False
                mfa_details.append("No active administrative users registered yet.")
            else:
                for u in admins:
                    if not u.mfa_enabled:
                        mfa_passed = False
                        mfa_details.append(f"Admin '{u.username}' does not have MFA enabled.")
                    else:
                        mfa_details.append(f"Admin '{u.username}' MFA status: ENABLED")
        except Exception as e:
            mfa_passed = False
            mfa_details = [f"Could not load users list: {e}"]

        # 2. mTLS Check for Nodes
        try:
            nodes = self.registry.node_service.list_nodes()
            mtls_passed = True
            mtls_details = []
            
            if not nodes:
                mtls_passed = False
                mtls_details.append("No node hosts registered yet.")
            else:
                for n in nodes:
                    if not getattr(n, "public_key", None):
                        mtls_passed = False
                        mtls_details.append(f"Node '{n.hostname}' public key/cert missing.")
                    else:
                        mtls_details.append(f"Node '{n.hostname}' mTLS status: CONFIGURED")
        except Exception as e:
            mtls_passed = False
            mtls_details = [f"Could not load nodes list: {e}"]

        # 3. Transmission Encryption Check (Secure Aggregation active on enabled policies)
        try:
            policies = self.registry.policy_service.list_policies()
            secagg_passed = True
            secagg_details = []
            enabled_policies = [p for p in policies if p.status == "Enabled"]
            
            if not enabled_policies:
                secagg_passed = False
                secagg_details.append("No active governance policies configured yet.")
            else:
                for p in enabled_policies:
                    if not p.secagg_enabled:
                        secagg_passed = False
                        secagg_details.append(f"Policy '{p.name}' does not enforce Secure Aggregation.")
                    else:
                        secagg_details.append(f"Policy '{p.name}' Secure Aggregation: ENFORCED")
        except Exception as e:
            secagg_passed = False
            secagg_details = [f"Could not load policies list: {e}"]

        # 4. Audit Controls Check
        try:
            events = self.registry.audit_service.get_all_events()
            audit_passed = len(events) > 0
            audit_details = [f"Total logged governance events in audit trail: {len(events)}"]
        except Exception as e:
            audit_passed = False
            audit_details = [f"Could not read audit logs: {e}"]

        # Calculate score
        checks = [
            {"name": "MFA for Administrative Access", "passed": mfa_passed, "details": mfa_details, "safeguard": "§ 164.308(a)(4)"},
            {"name": "mTLS Host Identity Verification", "passed": mtls_passed, "details": mtls_details, "safeguard": "§ 164.312(a)(1)"},
            {"name": "Transmission Security (Secure Aggregation)", "passed": secagg_passed, "details": secagg_details, "safeguard": "§ 164.312(e)(1)"},
            {"name": "Governance Audit Controls Logging", "passed": audit_passed, "details": audit_details, "safeguard": "§ 164.312(b)"}
        ]
        
        passed_count = sum(1 for c in checks if c["passed"])
        score = int((passed_count / len(checks)) * 100.0)
        
        # Log compliance check event
        try:
            self.registry.audit_service.log_event(
                event_type="HIPAA_AUDIT_RUN",
                resource_type="Compliance",
                resource_name="HIPAA",
                action="audit",
                status="Success",
                message=f"HIPAA compliance audit run completed. Readiness score: {score}%."
            )
        except Exception:
            pass

        return {
            "framework": "HIPAA",
            "timestamp": datetime.now().isoformat(),
            "readiness_score": score,
            "checks": checks
        }

    def audit_gdpr(self) -> dict:
        """
        Runs security audit checks matching EU GDPR standards:
        - Article 5(1)(c): Data Minimization (Differential Privacy enabled & epsilon bounds check)
        - Article 7: Conditions for Consent (Consent presence & validity check on active clients)
        - Article 17: Right to Erasure / Right to be Forgotten (Revoked nodes excluded from runs)
        - Article 32: Security of Processing (Secure Aggregation active on policies)
        """
        # 1. Data Minimization (Differential Privacy Checks)
        try:
            policies = self.registry.policy_service.list_policies()
            enabled_policies = [p for p in policies if p.status == "Enabled"]
            dp_passed = True
            dp_details = []
            
            if not enabled_policies:
                dp_passed = False
                dp_details.append("No active governance policies configured yet.")
            else:
                for p in enabled_policies:
                    if not p.dp_enabled:
                        dp_passed = False
                        dp_details.append(f"Policy '{p.name}' does not enforce Differential Privacy.")
                    elif p.dp_epsilon > 5.0:
                        dp_passed = False
                        dp_details.append(f"Policy '{p.name}' has weak privacy budget (epsilon: {p.dp_epsilon} > 5.0).")
                    else:
                        dp_details.append(f"Policy '{p.name}' Differential Privacy Epsilon: {p.dp_epsilon} (SAFE)")
        except Exception as e:
            dp_passed = False
            dp_details = [f"Could not load policies list: {e}"]

        # 2. Conditions for Consent (Integrity check for active training runs)
        try:
            sessions = self.registry.training_service.list_sessions()
            active_sessions = [s for s in sessions if s.status == "Running"]
            consent_passed = True
            consent_details = []
            
            # Fetch all consents
            consents = self.registry.consent_service.repository.find_all()
            consent_map = {} # (client_id, dataset_name) -> status
            for c in consents:
                consent_map[(c.client_id, c.dataset_name.lower())] = c.status
            
            # Fetch all clients to map name -> id
            clients = self.registry.client_service.repository.find_all()
            client_id_map = {c.name.lower(): c.id for c in clients}
            
            if not active_sessions:
                consent_details.append("No active running federated learning sessions to audit.")
            else:
                for s in active_sessions:
                    ds = s.dataset_name.lower()
                    for client_name in s.participating_clients:
                        c_id = client_id_map.get(client_name.lower(), client_name)
                        status = consent_map.get((c_id, ds))
                        if not status:
                            consent_passed = False
                            consent_details.append(f"Session '{s.name}': Client '{client_name}' participating without consent record for dataset '{s.dataset_name}'.")
                        elif status == "Revoked":
                            consent_passed = False
                            consent_details.append(f"Session '{s.name}': Client '{client_name}' participating but consent for dataset '{s.dataset_name}' is REVOKED.")
                        else:
                            consent_details.append(f"Session '{s.name}': Client '{client_name}' consent status: GRANTED")
        except Exception as e:
            consent_passed = False
            consent_details = [f"Could not audit consent records: {e}"]

        # 3. Right to Erasure / Right to be Forgotten Enforcements
        try:
            erasure_passed = True
            erasure_details = []
            
            revoked_consents = [c for c in consents if c.status == "Revoked"]
            if not revoked_consents:
                erasure_details.append("No revoked consent records found in system registry.")
            else:
                for rc in revoked_consents:
                    c_name = rc.client_id
                    for cl in clients:
                        if cl.id == rc.client_id:
                            c_name = cl.name
                            break
                    
                    ds = rc.dataset_name.lower()
                    for s in active_sessions:
                        if s.dataset_name.lower() == ds and c_name in s.participating_clients:
                            erasure_passed = False
                            erasure_details.append(f"Client '{c_name}' has revoked consent for '{rc.dataset_name}' but is participating in running session '{s.name}'.")
                    
                    if erasure_passed:
                        erasure_details.append(f"Client '{c_name}' consent revocation for '{rc.dataset_name}' successfully enforced.")
        except Exception as e:
            erasure_passed = False
            erasure_details = [f"Could not verify erasure status: {e}"]

        # 4. Security of Processing (Secure Aggregation active on enabled policies)
        try:
            secagg_passed = True
            secagg_details = []
            
            if not enabled_policies:
                secagg_passed = False
                secagg_details.append("No active governance policies configured yet.")
            else:
                for p in enabled_policies:
                    if not p.secagg_enabled:
                        secagg_passed = False
                        secagg_details.append(f"Policy '{p.name}' does not enforce Secure Aggregation.")
                    else:
                        secagg_details.append(f"Policy '{p.name}' Secure Aggregation: ENFORCED")
        except Exception as e:
            secagg_passed = False
            secagg_details = [f"Could not audit policy security levels: {e}"]

        # Calculate score
        checks = [
            {"name": "Data Minimization (Differential Privacy)", "passed": dp_passed, "details": dp_details, "safeguard": "Article 5(1)(c)"},
            {"name": "Conditions for Consent Validation", "passed": consent_passed, "details": consent_details, "safeguard": "Article 7"},
            {"name": "Right to Erasure Enforcement", "passed": erasure_passed, "details": erasure_details, "safeguard": "Article 17"},
            {"name": "Security of Processing (SecAgg)", "passed": secagg_passed, "details": secagg_details, "safeguard": "Article 32"}
        ]
        
        passed_count = sum(1 for c in checks if c["passed"])
        score = int((passed_count / len(checks)) * 100.0)
        
        # Log compliance check event
        try:
            self.registry.audit_service.log_event(
                event_type="GDPR_AUDIT_RUN",
                resource_type="Compliance",
                resource_name="GDPR",
                action="audit",
                status="Success",
                message=f"GDPR compliance audit run completed. Readiness score: {score}%."
            )
        except Exception:
            pass

        return {
            "framework": "GDPR",
            "timestamp": datetime.now().isoformat(),
            "readiness_score": score,
            "checks": checks
        }
