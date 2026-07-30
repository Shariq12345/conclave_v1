import unittest

import numpy as np

from conclave.integrations.flower.orchestrator import CryptographicSecAgg
from conclave.integrations.flower.threshold_secagg import (
    ShamirSecretSharing,
    ThresholdSecAggContext,
)


class ThresholdSecAggTests(unittest.TestCase):
    def test_shamir_recovers_secret_at_threshold(self):
        secret = bytes(range(32))
        shares = ShamirSecretSharing.split(secret, threshold=3, share_count=5)
        self.assertEqual(ShamirSecretSharing.recover([shares[0], shares[2], shares[4]], 32), secret)

    def test_dropout_masks_are_removed_with_threshold_shares(self):
        names = ["hospital-a", "hospital-b", "hospital-c"]
        context = ThresholdSecAggContext.create(names, threshold=2)
        updates = {
            "hospital-a": [np.array([1.0, 2.0], dtype=np.float32)],
            "hospital-b": [np.array([3.0, 4.0], dtype=np.float32)],
            "hospital-c": [np.array([5.0, 6.0], dtype=np.float32)],
        }
        active = ["hospital-a", "hospital-c"]
        masked_sum = [np.zeros(2, dtype=np.float32)]
        for name in active:
            index = names.index(name)
            masked = CryptographicSecAgg.apply_pairwise_masks(
                client_name=name,
                my_idx=index,
                client_names=names,
                parameters=updates[name],
                keypairs=context.keypairs,
            )
            masked_sum[0] += masked[0]

        restored = context.remove_dropped_client_masks(
            masked_sum,
            active_clients=active,
            dropped_clients=["hospital-b"],
            responding_clients=active,
        )
        np.testing.assert_allclose(restored[0], updates["hospital-a"][0] + updates["hospital-c"][0], atol=1e-5)

    def test_recovery_fails_below_threshold(self):
        context = ThresholdSecAggContext.create(["a", "b", "c", "d"], threshold=2)
        with self.assertRaises(ValueError):
            context.reconstruct_dropped_private_key("a", ["b"])


if __name__ == "__main__":
    unittest.main()
