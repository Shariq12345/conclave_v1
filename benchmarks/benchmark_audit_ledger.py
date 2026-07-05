#!/usr/bin/env python3
"""
conclave.benchmarks.benchmark_audit_ledger
─────────────────────────────────────────────
Cryptographic Audit Ledger Scalability benchmark.
Measures append performance and verification latency as the SHA-256 hash chain grows.
Tests integrity validation by temporarily corrupting entries and verifying detection times.

Saves metrics in a CSV and generates publication-quality figures.
"""

import os
import sys
import time
import csv
import logging
import argparse
import random
import uuid
import hashlib
from datetime import datetime
from typing import List, Dict, Any

import numpy as np
import psutil
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("conclave_audit_bench")


def set_reproducible_seed(seed: int):
    """Sets seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    logger.info(f"Reproducible random seed set to: {seed}")


class AuditRecord:
    """Represents a cryptographically linked ledger event record matching Conclave production."""
    def __init__(
        self,
        event_type: str,
        resource_type: str,
        resource_name: str,
        action: str,
        status: str,
        message: str,
        previous_hash: str,
        timestamp: datetime = None,
        event_id: str = None
    ):
        self.id = event_id or str(uuid.uuid4())
        self.timestamp = timestamp or datetime.now()
        self.event_type = event_type.strip()
        self.resource_type = resource_type.strip()
        self.resource_name = resource_name.strip()
        self.action = action.strip()
        self.status = status.strip()
        self.message = message.strip()
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        """Computes SHA-256 hash of the record contents linked to the previous block's hash."""
        ph = self.previous_hash or "0"
        ts_str = self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp)
        payload = f"{ts_str}_{self.event_type}_{self.resource_type}_{self.resource_name}_{self.action}_{self.status}_{self.message}_{ph}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_single_audit_benchmark(C: int) -> Dict[str, Any]:
    """Runs a single ledger append, verify, and tamper detection iteration for size C."""
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / (1024 * 1024)
    
    # 1. Append sequentially
    ledger: List[AuditRecord] = []
    prev_hash = "0"
    
    t_append_start = time.perf_counter()
    for i in range(C):
        record = AuditRecord(
            event_type="NODE_HEARTBEAT",
            resource_type="Node",
            resource_name=f"node_{i}",
            action="heartbeat",
            status="Success",
            message=f"Cryptographic node heartbeat report at index {i}",
            previous_hash=prev_hash,
            timestamp=datetime.now()
        )
        ledger.append(record)
        prev_hash = record.hash
    t_append_end = time.perf_counter()
    append_time_ms = (t_append_end - t_append_start) * 1000.0
    append_throughput = C / (t_append_end - t_append_start) if (t_append_end - t_append_start) > 0 else 0
    
    # 2. Verify complete chain
    t_verify_start = time.perf_counter()
    expected_prev_hash = "0"
    for record in ledger:
        # Check chain link
        if record.previous_hash != expected_prev_hash:
            raise ValueError(f"Previous hash mismatch. Expected: {expected_prev_hash}, Found: {record.previous_hash}")
        # Check block hash
        calculated = record.calculate_hash()
        if record.hash != calculated:
            raise ValueError(f"Block data mismatch. Hash: {record.hash}, Calculated: {calculated}")
        expected_prev_hash = record.hash
    t_verify_end = time.perf_counter()
    verify_time_ms = (t_verify_end - t_verify_start) * 1000.0
    verify_throughput = C / (t_verify_end - t_verify_start) if (t_verify_end - t_verify_start) > 0 else 0
    
    # Peak Memory tracking
    mem_after = process.memory_info().rss / (1024 * 1024)
    peak_mem_mb = max(mem_before, mem_after)
    
    # 3. Tampering Integrity Validation Test
    tamper_idx = random.randint(0, C - 1)
    original_msg = ledger[tamper_idx].message
    
    # Temporarily corrupt entry
    ledger[tamper_idx].message = original_msg + "_tampered_by_attacker"
    
    # Measure time required to detect corruption
    t_detect_start = time.perf_counter()
    tampering_detected = False
    expected_prev_hash = "0"
    for idx, record in enumerate(ledger):
        if record.previous_hash != expected_prev_hash or record.hash != record.calculate_hash():
            tampering_detected = True
            break
        expected_prev_hash = record.hash
    t_detect_end = time.perf_counter()
    detect_time_ms = (t_detect_end - t_detect_start) * 1000.0
    
    # Restore original record message
    ledger[tamper_idx].message = original_msg
    
    return {
        "chain_size": C,
        "append_time_ms": append_time_ms,
        "append_logs_per_sec": append_throughput,
        "verification_ms": verify_time_ms,
        "verification_logs_per_sec": verify_throughput,
        "peak_memory_mb": peak_mem_mb,
        "tampering_detected": tampering_detected,
        "corruption_detection_ms": detect_time_ms
    }


def generate_figures(results: List[Dict[str, Any]]):
    """Generates four publication-quality overhead figures using Matplotlib."""
    logger.info("Generating publication-quality audit ledger graphs...")
    
    import matplotlib.pyplot as plt
    
    sizes = [r["chain_size"] for r in results]
    size_labels = [f"{s:,}" for s in sizes]
    
    append_tp = [r["append_logs_per_sec"] for r in results]
    verify_ms = [r["verification_ms"] for r in results]
    verify_tp = [r["verification_logs_per_sec"] for r in results]
    mem = [r["peak_memory_mb"] for r in results]
    
    os.makedirs("figures", exist_ok=True)
    
    # Premium theme configurations
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "axes.edgecolor": "#D1D5DB",
        "axes.linewidth": 0.8,
        "grid.color": "#E5E7EB",
        "grid.linewidth": 0.5,
        "xtick.color": "#4B5563",
        "ytick.color": "#4B5563",
        "text.color": "#1F2937"
    })
    
    def style_ax(ax, title, ylabel):
        ax.set_title(title, fontsize=12, fontweight="bold", pad=12)
        ax.set_xlabel("Ledger Chain Size (Records)", fontsize=10, labelpad=8)
        ax.set_ylabel(ylabel, fontsize=10, labelpad=8)
        
        # Logarithmic or uniform ticks spacing
        ax.set_xscale("log")
        ax.set_xticks(sizes)
        ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
        ax.set_xticklabels(size_labels)
        
        ax.grid(True, linestyle="--", alpha=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#9CA3AF")
        ax.spines["bottom"].set_color("#9CA3AF")

    # --- Figure 1: Chain Size vs Append Throughput ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(sizes, append_tp, marker="o", markersize=6, color="#4F46E5", linewidth=2.0)
    style_ax(ax, "Append Throughput vs. Chain Size", "Throughput (logs/sec)")
    plt.tight_layout()
    plt.savefig("figures/audit_ledger_append_throughput.png", dpi=300)
    plt.savefig("figures/audit_ledger_append_throughput.svg", format="svg")
    plt.savefig("figures/audit_ledger_append_throughput.pdf", format="pdf")
    plt.close()
    
    # --- Figure 2: Chain Size vs Verification Time ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(sizes, verify_ms, marker="s", markersize=6, color="#EF4444", linewidth=2.0)
    style_ax(ax, "Verification Duration vs. Chain Size", "Verification Time (ms)")
    plt.tight_layout()
    plt.savefig("figures/audit_ledger_verification_time.png", dpi=300)
    plt.savefig("figures/audit_ledger_verification_time.svg", format="svg")
    plt.savefig("figures/audit_ledger_verification_time.pdf", format="pdf")
    plt.close()
    
    # --- Figure 3: Chain Size vs Verification Throughput ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(sizes, verify_tp, marker="^", markersize=6, color="#06B6D4", linewidth=2.0)
    style_ax(ax, "Verification Throughput vs. Chain Size", "Throughput (logs/sec)")
    plt.tight_layout()
    plt.savefig("figures/audit_ledger_verification_throughput.png", dpi=300)
    plt.savefig("figures/audit_ledger_verification_throughput.svg", format="svg")
    plt.savefig("figures/audit_ledger_verification_throughput.pdf", format="pdf")
    plt.close()
    
    # --- Figure 4: Chain Size vs Peak Memory Usage ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(sizes, mem, marker="d", markersize=6, color="#F59E0B", linewidth=2.0)
    style_ax(ax, "Peak Memory Usage vs. Chain Size", "Peak Memory (MB)")
    plt.tight_layout()
    plt.savefig("figures/audit_ledger_memory_usage.png", dpi=300)
    plt.savefig("figures/audit_ledger_memory_usage.svg", format="svg")
    plt.savefig("figures/audit_ledger_memory_usage.pdf", format="pdf")
    plt.close()
    
    logger.info("Audit ledger graphs successfully generated in PNG, SVG, and PDF formats.")


def main():
    parser = argparse.ArgumentParser(description="Conclave Cryptographic Audit Ledger Scalability Benchmark")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()
    
    logger.info("Starting Conclave Cryptographic Audit Ledger Scalability Benchmark...")
    set_reproducible_seed(args.seed)
    
    chain_sizes = [500, 5000, 10000, 25000, 50000]
    repetitions = 5
    results = []
    
    for C in tqdm(chain_sizes, desc="Benchmarking Ledger Chain Size", unit="size"):
        logger.info(f"Evaluating chain size: {C:,} entries over {repetitions} runs...")
        
        rep_metrics = []
        for r in range(repetitions):
            metrics = run_single_audit_benchmark(C)
            rep_metrics.append(metrics)
            
        # Compute average metrics across repetitions
        avg_metrics = {
            "chain_size": C,
            "append_time_ms": round(sum(m["append_time_ms"] for m in rep_metrics) / repetitions, 3),
            "append_logs_per_sec": round(sum(m["append_logs_per_sec"] for m in rep_metrics) / repetitions, 1),
            "verification_ms": round(sum(m["verification_ms"] for m in rep_metrics) / repetitions, 3),
            "verification_logs_per_sec": round(sum(m["verification_logs_per_sec"] for m in rep_metrics) / repetitions, 1),
            "peak_memory_mb": round(max(m["peak_memory_mb"] for m in rep_metrics), 1),
            "tampering_detected": all(m["tampering_detected"] for m in rep_metrics),
            "corruption_detection_ms": round(sum(m["corruption_detection_ms"] for m in rep_metrics) / repetitions, 3)
        }
        results.append(avg_metrics)
        logger.info(f"Avg Result for {C:,} entries: {avg_metrics}")
        
    # Write to CSV
    os.makedirs("results", exist_ok=True)
    csv_file = "results/audit_ledger_scalability.csv"
    
    keys = ["chain_size", "append_time_ms", "append_logs_per_sec", "verification_ms", "verification_logs_per_sec", "peak_memory_mb", "tampering_detected", "corruption_detection_ms"]
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
        
    logger.info(f"CSV data written to {csv_file}")
    
    # Generate Plots
    generate_figures(results)
    
    logger.info("Benchmark complete!")


if __name__ == "__main__":
    main()
