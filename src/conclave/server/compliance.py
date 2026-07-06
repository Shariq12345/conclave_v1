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
