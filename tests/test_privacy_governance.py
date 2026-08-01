"""
tests.test_privacy_governance
───────────────────────────────
Unit tests for Organization Differential Privacy budget tracking,
database persistence, and automated governance enforcement.
"""

import unittest
from datetime import datetime
from conclave.models import Organization, Policy, TrainingSession
from conclave.server.services import (
    GovernanceService, PolicyService, ClientService, ConsentService, OrganizationService
)
from conclave.server.storage import (
    SQLiteOrganizationRepository, SQLitePolicyRepository, SQLiteClientRepository,
    SQLiteConsentRepository, SQLiteAuditRepository
)
from conclave.server.database import init_db, SessionLocal


class TestPrivacyGovernance(unittest.TestCase):

    def setUp(self):
        init_db()
        self.session_factory = SessionLocal
        self.org_repo = SQLiteOrganizationRepository(self.session_factory)
        self.audit_repo = SQLiteAuditRepository(self.session_factory)
        self.policy_repo = SQLitePolicyRepository(self.session_factory)
        self.client_repo = SQLiteClientRepository(self.session_factory)
        self.consent_repo = SQLiteConsentRepository(self.session_factory)

        from conclave.server.services import AuditService
        self.audit_service = AuditService(self.audit_repo)
        self.org_service = OrganizationService(self.org_repo, self.audit_service)
        self.policy_service = PolicyService(self.policy_repo, self.audit_service)
        self.client_service = ClientService(self.client_repo, self.audit_service)
        self.consent_service = ConsentService(self.consent_repo, self.client_service, self.audit_service)

        self.governance_service = GovernanceService(
            self.client_service, self.policy_service, self.consent_service, self.org_service
        )

    def test_organization_privacy_budget_persistence(self):
        org_name = f"test_org_privacy_{datetime.now().timestamp()}"
        org = Organization(name=org_name, organization_type="Hospital", max_epsilon=4.0, consumed_epsilon=1.0)
        saved = self.org_repo.save(org)

        self.assertTrue(saved.has_available_privacy_budget(2.0))
        self.assertFalse(saved.has_available_privacy_budget(4.0))

        # Consume budget and verify persistence
        saved.consume_privacy_budget(2.5)
        self.org_repo.save(saved)

        reloaded = self.org_repo.find_by_name(org_name)
        self.assertIsNotNone(reloaded)
        self.assertAlmostEqual(reloaded.consumed_epsilon, 3.5, places=2)
        self.assertFalse(reloaded.has_available_privacy_budget(1.0))


if __name__ == "__main__":
    unittest.main()
