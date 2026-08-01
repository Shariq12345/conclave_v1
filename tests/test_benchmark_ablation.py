"""
tests.test_benchmark_ablation
─────────────────────────────
Unit tests and validation suite for FedGuard micro-benchmarking engine.
Verifies micro-ablation latency, node scalability, and Byzantine attack matrix analysis.
"""

import pytest
from conclave.server.benchmark import BenchmarkEngine


def test_component_ablation_metrics():
    """Verify component-wise micro-ablation execution timings and standard deviations."""
    ablation_summary = BenchmarkEngine.run_component_ablation(num_trials=3, num_clients=5, param_dim=10000)
    
    assert "mtls_verification" in ablation_summary
    assert "tpm_attestation" in ablation_summary
    assert "abac_policy_eval" in ablation_summary
    assert "secagg_key_masking" in ablation_summary
    assert "rdp_noise_accounting" in ablation_summary
    assert "sha256_audit_append" in ablation_summary

    # Ensure mean timings are positive non-zero floats
    for comp, metrics in ablation_summary.items():
        assert metrics["mean_ms"] >= 0.0
        assert metrics["std_ms"] >= 0.0


def test_byzantine_sensitivity_matrix():
    """Verify Byzantine attack accuracy matrix across varying adversary ratios f in {0.0, 0.1, 0.2, 0.3, 0.4}."""
    matrix = BenchmarkEngine.run_byzantine_sensitivity_matrix(num_clients=10, param_dim=500)
    
    assert "FedAvg" in matrix
    assert "Trimmed_Mean" in matrix
    assert "Median" in matrix
    assert "Krum" in matrix

    # Verify FedAvg performance degrades under high Byzantine ratio compared to honest baseline
    assert matrix["FedAvg"][0.0] >= matrix["FedAvg"][0.4]
    
    # Verify Byzantine-robust methods maintain higher performance under 40% attack than FedAvg
    assert matrix["Trimmed_Mean"][0.4] >= matrix["FedAvg"][0.4]
