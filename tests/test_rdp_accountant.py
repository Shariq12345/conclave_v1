"""Tests for the Rényi Differential Privacy accountant."""

import math
import unittest

from conclave.integrations.flower.privacy import (
    GaussianRDPAccountant,
    _compute_rdp_gaussian,
    _compute_rdp_composed,
    _rdp_to_dp,
)


class TestRDPGaussianMechanism(unittest.TestCase):
    """Unit tests for the per-step Gaussian RDP computation."""

    def test_rdp_formula_at_known_values(self):
        # rdp(α) = α / (2σ²)
        # σ=1.0, α=2.0 → 2 / (2*1) = 1.0
        self.assertAlmostEqual(_compute_rdp_gaussian(1.0, 2.0), 1.0)
        # σ=2.0, α=4.0 → 4 / (2*4) = 0.5
        self.assertAlmostEqual(_compute_rdp_gaussian(2.0, 4.0), 0.5)

    def test_rdp_increases_with_alpha(self):
        eps_low = _compute_rdp_gaussian(1.0, 2.0)
        eps_high = _compute_rdp_gaussian(1.0, 10.0)
        self.assertGreater(eps_high, eps_low)

    def test_rdp_decreases_with_sigma(self):
        eps_low_noise = _compute_rdp_gaussian(0.5, 5.0)
        eps_high_noise = _compute_rdp_gaussian(2.0, 5.0)
        self.assertGreater(eps_low_noise, eps_high_noise)

    def test_invalid_alpha_raises(self):
        with self.assertRaises(ValueError):
            _compute_rdp_gaussian(1.0, 1.0)
        with self.assertRaises(ValueError):
            _compute_rdp_gaussian(1.0, 0.5)

    def test_invalid_sigma_raises(self):
        with self.assertRaises(ValueError):
            _compute_rdp_gaussian(0.0, 2.0)
        with self.assertRaises(ValueError):
            _compute_rdp_gaussian(-1.0, 2.0)


class TestRDPComposition(unittest.TestCase):
    """Tests for sequential composition."""

    def test_composition_is_linear(self):
        single = _compute_rdp_gaussian(1.0, 3.0)
        composed = _compute_rdp_composed(1.0, 3.0, 10)
        self.assertAlmostEqual(composed, 10 * single)

    def test_single_step_equals_base(self):
        base = _compute_rdp_gaussian(2.0, 5.0)
        composed = _compute_rdp_composed(2.0, 5.0, 1)
        self.assertAlmostEqual(composed, base)


class TestRDPToDPConversion(unittest.TestCase):
    """Tests for the RDP → (ε, δ)-DP conversion."""

    def test_conversion_returns_finite_for_valid_inputs(self):
        eps = _rdp_to_dp(1.0, 2.0, 1e-5)
        self.assertTrue(math.isfinite(eps))
        self.assertGreater(eps, 0)

    def test_smaller_delta_gives_larger_epsilon(self):
        eps_tight = _rdp_to_dp(1.0, 5.0, 1e-3)
        eps_loose = _rdp_to_dp(1.0, 5.0, 1e-8)
        self.assertGreater(eps_loose, eps_tight)

    def test_zero_delta_returns_inf(self):
        eps = _rdp_to_dp(1.0, 2.0, 0.0)
        self.assertEqual(eps, math.inf)

    def test_larger_rdp_eps_gives_larger_dp_eps(self):
        eps_small = _rdp_to_dp(0.5, 3.0, 1e-5)
        eps_large = _rdp_to_dp(5.0, 3.0, 1e-5)
        self.assertGreater(eps_large, eps_small)


class TestGaussianRDPAccountant(unittest.TestCase):
    """Integration tests for the full accountant."""

    def test_epsilon_returns_pair(self):
        acc = GaussianRDPAccountant(noise_multiplier=1.0, delta=1e-5)
        eps, alpha = acc.epsilon(num_steps=5)
        self.assertIsInstance(eps, float)
        self.assertIsInstance(alpha, float)
        self.assertGreater(eps, 0)
        self.assertGreater(alpha, 1)

    def test_epsilon_increases_with_steps(self):
        acc = GaussianRDPAccountant(noise_multiplier=1.0, delta=1e-5)
        eps_1, _ = acc.epsilon(1)
        eps_10, _ = acc.epsilon(10)
        eps_100, _ = acc.epsilon(100)
        self.assertLess(eps_1, eps_10)
        self.assertLess(eps_10, eps_100)

    def test_more_noise_gives_smaller_epsilon(self):
        acc_low = GaussianRDPAccountant(noise_multiplier=0.5, delta=1e-5)
        acc_high = GaussianRDPAccountant(noise_multiplier=5.0, delta=1e-5)
        eps_low, _ = acc_low.epsilon(10)
        eps_high, _ = acc_high.epsilon(10)
        self.assertGreater(eps_low, eps_high)

    def test_zero_steps_returns_zero(self):
        acc = GaussianRDPAccountant(noise_multiplier=1.0, delta=1e-5)
        eps, _ = acc.epsilon(0)
        self.assertEqual(eps, 0.0)

    def test_invalid_constructor_args(self):
        with self.assertRaises(ValueError):
            GaussianRDPAccountant(noise_multiplier=0.0, delta=1e-5)
        with self.assertRaises(ValueError):
            GaussianRDPAccountant(noise_multiplier=1.0, delta=0.0)
        with self.assertRaises(ValueError):
            GaussianRDPAccountant(noise_multiplier=1.0, delta=1.0)

    def test_epsilon_per_order_returns_full_table(self):
        acc = GaussianRDPAccountant(noise_multiplier=1.0, delta=1e-5)
        table = acc.epsilon_per_order(5)
        self.assertEqual(len(table), len(acc.orders))
        for alpha, rdp_eps, dp_eps in table:
            self.assertGreater(alpha, 1)
            self.assertGreater(rdp_eps, 0)


class TestNoiseCalibration(unittest.TestCase):
    """Tests for the binary-search noise multiplier calibration."""

    def test_calibrated_sigma_achieves_target(self):
        target_eps = 2.0
        delta = 1e-5
        num_steps = 10
        sigma = GaussianRDPAccountant.calibrate_noise_multiplier(
            target_eps, delta, num_steps
        )
        acc = GaussianRDPAccountant(sigma, delta)
        achieved_eps, _ = acc.epsilon(num_steps)
        # The achieved ε should be ≤ target (within small tolerance from rounding)
        self.assertLessEqual(achieved_eps, target_eps + 0.01)
        # And should be reasonably close (not wildly conservative)
        self.assertGreater(achieved_eps, target_eps * 0.5)

    def test_tighter_budget_requires_more_noise(self):
        delta = 1e-5
        num_steps = 10
        sigma_loose = GaussianRDPAccountant.calibrate_noise_multiplier(8.0, delta, num_steps)
        sigma_tight = GaussianRDPAccountant.calibrate_noise_multiplier(1.0, delta, num_steps)
        self.assertGreater(sigma_tight, sigma_loose)

    def test_more_steps_require_more_noise(self):
        delta = 1e-5
        target_eps = 2.0
        sigma_few = GaussianRDPAccountant.calibrate_noise_multiplier(target_eps, delta, 5)
        sigma_many = GaussianRDPAccountant.calibrate_noise_multiplier(target_eps, delta, 50)
        self.assertGreater(sigma_many, sigma_few)

    def test_invalid_target_epsilon_raises(self):
        with self.assertRaises(ValueError):
            GaussianRDPAccountant.calibrate_noise_multiplier(0.0, 1e-5, 10)
        with self.assertRaises(ValueError):
            GaussianRDPAccountant.calibrate_noise_multiplier(-1.0, 1e-5, 10)

    def test_invalid_num_steps_raises(self):
        with self.assertRaises(ValueError):
            GaussianRDPAccountant.calibrate_noise_multiplier(1.0, 1e-5, 0)


class TestConclaveDPFedAvgIntegration(unittest.TestCase):
    """Verify that the accountant satisfies the DPFedAvg API contract."""

    def test_matches_orchestrator_usage_pattern(self):
        """Reproduce the exact call sequence from DPFedAvg.__init__ and aggregate_fit."""
        # Simulate DPFedAvg constructor
        dp_epsilon = 2.0
        dp_delta = 1e-5
        num_rounds = 5

        noise_multiplier = GaussianRDPAccountant.calibrate_noise_multiplier(
            dp_epsilon, dp_delta, num_rounds
        )
        self.assertGreater(noise_multiplier, 0)

        accountant = GaussianRDPAccountant(noise_multiplier, dp_delta)

        # Simulate _record_privacy_budget for each round
        for server_round in range(1, num_rounds + 1):
            accumulated_rdp_eps, renyi_order = accountant.epsilon(server_round)
            self.assertIsInstance(accumulated_rdp_eps, float)
            self.assertIsInstance(renyi_order, float)
            self.assertGreater(accumulated_rdp_eps, 0)
            self.assertGreater(renyi_order, 1)

        # Final epsilon should be within budget
        final_eps, _ = accountant.epsilon(num_rounds)
        self.assertLessEqual(final_eps, dp_epsilon + 0.01)


if __name__ == "__main__":
    unittest.main()
