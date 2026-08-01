"""
tests.test_robust_aggregation
───────────────────────────────
Unit tests for Byzantine robust aggregation algorithms (Trimmed Mean,
Coordinate Median, Krum) and Byzantine Anomaly Detector.
"""

import unittest
import numpy as np

from conclave.integrations.flower.robust_aggregation import (
    TrimmedMeanAggregator,
    CoordinateMedianAggregator,
    KrumAggregator,
    ByzantineAnomalyDetector
)


class TestRobustAggregation(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        # Create 5 client updates with 10 parameters each
        # Clients 0, 1, 2, 3 are honest (near 1.0)
        # Client 4 is adversarial (sign-flipped -5.0)
        self.honest_updates = [
            [np.full((10,), 1.0, dtype=np.float32)],
            [np.full((10,), 1.1, dtype=np.float32)],
            [np.full((10,), 0.9, dtype=np.float32)],
            [np.full((10,), 1.05, dtype=np.float32)],
        ]
        self.byzantine_update = [np.full((10,), -5.0, dtype=np.float32)]
        self.all_updates = self.honest_updates + [self.byzantine_update]

    def test_trimmed_mean_aggregator(self):
        aggregator = TrimmedMeanAggregator(trim_ratio=0.2)
        result = aggregator.aggregate(self.all_updates)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].shape, (10,))
        # Trimmed mean removes highest and lowest client, resulting in clean honest mean ~1.0
        mean_val = float(np.mean(result[0]))
        self.assertAlmostEqual(mean_val, 0.9833, places=2)

    def test_coordinate_median_aggregator(self):
        aggregator = CoordinateMedianAggregator()
        result = aggregator.aggregate(self.all_updates)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].shape, (10,))
        # Median of [1.0, 1.1, 0.9, 1.05, -5.0] is 1.0
        median_val = float(np.median(result[0]))
        self.assertAlmostEqual(median_val, 1.0, places=2)

    def test_krum_aggregator(self):
        aggregator = KrumAggregator(f_byzantine=1)
        result = aggregator.aggregate(self.all_updates)

        self.assertEqual(len(result), 1)
        # Krum selects an honest update vector instead of the byzantine vector
        self.assertGreater(float(np.mean(result[0])), 0.0)

    def test_byzantine_anomaly_detector(self):
        detector = ByzantineAnomalyDetector(cosine_threshold=-0.1, max_l2_ratio=3.0)

        updates_map = {
            "client_0": self.honest_updates[0],
            "client_1": self.honest_updates[1],
            "client_2": self.honest_updates[2],
            "client_3": self.honest_updates[3],
            "client_byzantine": self.byzantine_update,
        }

        results = detector.detect_anomalies(updates_map)

        self.assertEqual(len(results), 5)
        self.assertFalse(results["client_0"]["is_anomalous"])
        self.assertFalse(results["client_1"]["is_anomalous"])
        self.assertTrue(results["client_byzantine"]["is_anomalous"])
        self.assertIn("Sign-Flipping", results["client_byzantine"]["reason"])


if __name__ == "__main__":
    unittest.main()
