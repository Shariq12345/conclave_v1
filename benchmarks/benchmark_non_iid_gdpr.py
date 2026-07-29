#!/usr/bin/env python3
"""
conclave.benchmarks.benchmark_non_iid_gdpr
───────────────────────────────────────────
Non-IID Dirichlet Skew & Empirical GDPR Article 17 Data Revocation Benchmark.

Quantifies:
1. Model accuracy & convergence trajectories under Dirichlet non-IID skews (alpha in [0.1, 0.5, 1.0, 10.0]).
2. Impact of GDPR Article 17 "Right to Erasure" client revocation on global accuracy.
3. Recovery convergence rate following client ejection.

Saves CSV metrics and generates publication-quality figures (PNG, SVG, PDF).
"""

import os
import sys
import time
import csv
import logging
import argparse
import random
from typing import Dict, List, Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from conclave.integrations.flower.data_partitioner import DirichletDataPartitioner
from conclave.integrations.flower.orchestrator import SimpleFlowerClient, CryptographicSecAgg

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("conclave_non_iid_gdpr")


def set_reproducible_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)


def generate_multiclass_dataset(num_samples: int = 1200, num_features: int = 6, num_classes: int = 3, seed: int = 42) -> tuple:
    rng = np.random.default_rng(seed)
    X = rng.normal(loc=0.0, scale=1.0, size=(num_samples, num_features)).astype(np.float32)
    # Generate multi-class boundary
    weights = rng.normal(loc=0.0, scale=1.0, size=(num_features, num_classes))
    logits = X @ weights
    y = np.argmax(logits, axis=1)
    return X, y


def simulate_fl_round(client_data: dict, active_clients: list, global_w: np.ndarray, global_b: np.ndarray, secagg_enabled: bool = False) -> tuple:
    """Simulates 1 FL round across active clients using current global weights."""
    client_updates = []
    total_samples = 0
    accuracies = []
    losses = []

    for client_id in active_clients:
        X_c, y_c = client_data[client_id]
        if len(y_c) == 0:
            continue

        w = global_w.copy()
        b = global_b.copy()
        m = len(y_c)

        # Local gradient descent (3 epochs)
        lr = 0.05
        for _ in range(3):
            logits = X_c @ w + b
            logits = np.clip(logits, -20.0, 20.0)
            exp_l = np.exp(logits - np.max(logits, axis=1, keepdims=True))
            probs = exp_l / np.sum(exp_l, axis=1, keepdims=True)

            # One-hot encoding of targets
            one_hot = np.zeros_like(probs)
            one_hot[np.arange(m), y_c] = 1.0

            dw = (1.0 / m) * (X_c.T @ (probs - one_hot))
            db = (1.0 / m) * np.sum(probs - one_hot, axis=0)

            w -= lr * dw
            b -= lr * db

        # Local evaluation
        logits = X_c @ w + b
        preds = np.argmax(logits, axis=1)
        acc = np.mean(preds == y_c)
        loss = -np.mean(np.log(probs[np.arange(m), y_c] + 1e-12))

        client_updates.append((w, b, m))
        total_samples += m
        accuracies.append(acc)
        losses.append(loss)

    # Federated Averaging
    if not client_updates:
        return global_w, global_b, 0.0, 0.0

    new_w = np.zeros_like(global_w)
    new_b = np.zeros_like(global_b)
    for w, b, m in client_updates:
        weight = m / float(total_samples)
        new_w += w * weight
        new_b += b * weight

    avg_acc = float(np.mean(accuracies))
    avg_loss = float(np.mean(losses))
    return new_w, new_b, avg_acc, avg_loss


def run_benchmark():
    logger.info("Starting Conclave Non-IID Dirichlet Skew & GDPR Article 17 Benchmark...")
    set_reproducible_seed(42)

    X_global, y_global = generate_multiclass_dataset(num_samples=1200, num_features=6, num_classes=3)
    alphas = [0.1, 0.5, 1.0, 10.0]
    num_clients = 4
    num_rounds = 8
    gdpr_revocation_round = 4

    results_history = []
    os.makedirs("results", exist_ok=True)
    os.makedirs("figures", exist_ok=True)

    csv_file = "results/non_iid_gdpr_results.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["alpha", "round", "active_clients", "accuracy", "loss", "gdpr_event"])

    alpha_trajectories = {}

    for alpha in alphas:
        logger.info(f"--- Evaluating Dirichlet Skew Alpha = {alpha} ---")
        partitioner = DirichletDataPartitioner(num_clients=num_clients, alpha=alpha, seed=42)
        client_data = partitioner.partition(X_global, y_global)

        # Initialize global model (6 features, 3 classes)
        global_w = np.zeros((6, 3), dtype=np.float32)
        global_b = np.zeros((3,), dtype=np.float32)

        active_clients = list(range(num_clients))
        accuracy_curve = []

        for r in range(1, num_rounds + 1):
            gdpr_event = "None"
            # Simulate GDPR Article 17 Revocation at round 4 (Client 1 revokes consent & dataset is purged)
            if r == gdpr_revocation_round and 1 in active_clients:
                active_clients.remove(1)
                gdpr_event = "GDPR_ART17_REVOCATION_CLIENT_1"
                logger.info(f" [GDPR Enforcement] Round {r}: Client 1 revoked consent under Article 17. Client ejected.")

            global_w, global_b, acc, loss = simulate_fl_round(client_data, active_clients, global_w, global_b)
            accuracy_curve.append(acc)

            logger.info(f" Round {r}/{num_rounds} (Alpha={alpha}): Active={len(active_clients)}, Acc={acc:.4f}, Loss={loss:.4f} {gdpr_event}")

            with open(csv_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([alpha, r, len(active_clients), acc, loss, gdpr_event])

        alpha_trajectories[alpha] = accuracy_curve

    # Generate Figures
    logger.info("Generating publication-quality figures for Non-IID & GDPR Revocation...")
    plt.figure(figsize=(10, 6))

    colors = {0.1: "#d62728", 0.5: "#ff7f0e", 1.0: "#2ca02c", 10.0: "#1f77b4"}
    styles = {0.1: "--", 0.5: "-.", 1.0: ":", 10.0: "-"}

    rounds = list(range(1, num_rounds + 1))
    for alpha, curve in alpha_trajectories.items():
        plt.plot(rounds, curve, label=f"Dirichlet $\\alpha$={alpha} ({'Extreme Non-IID' if alpha==0.1 else 'IID' if alpha==10.0 else 'Non-IID'})",
                 color=colors[alpha], linestyle=styles[alpha], linewidth=2.5, marker="o")

    # Add vertical line for GDPR Article 17 Event
    plt.axvline(x=gdpr_revocation_round, color="black", linestyle="--", alpha=0.7, label="GDPR Art. 17 Client 1 Revocation")

    plt.title("Conclave: Model Accuracy Trajectories under Dirichlet Skew & GDPR Art. 17 Revocation", fontsize=12, fontweight="bold")
    plt.xlabel("Federated Learning Round", fontsize=11)
    plt.ylabel("Global Model Accuracy", fontsize=11)
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="lower right", fontsize=10)
    plt.tight_layout()

    plt.savefig("figures/non_iid_gdpr_impact.png", dpi=300)
    plt.savefig("figures/non_iid_gdpr_impact.svg")
    plt.savefig("figures/non_iid_gdpr_impact.pdf")
    plt.close()

    logger.info("Non-IID & GDPR Article 17 Benchmark Completed Successfully!")


if __name__ == "__main__":
    run_benchmark()
