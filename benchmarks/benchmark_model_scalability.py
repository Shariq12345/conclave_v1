#!/usr/bin/env python3
"""
conclave.benchmarks.benchmark_model_scalability
────────────────────────────────────────────────
Scalability benchmark to measure how Conclave's aggregation,
serialization, and privacy mechanisms scale as the model size increases.

Saves metrics in a CSV and generates publication-quality figures.
"""

import os
import sys
import time
import csv
import logging
import argparse
import random
import concurrent.futures
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
logger = logging.getLogger("conclave_model_bench")


def set_reproducible_seed(seed: int):
    """Sets seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    logger.info(f"Reproducible random seed set to: {seed}")


def run_node_operations(node_idx: int, P: int, client_names: List[str]) -> Dict[str, Any]:
    """Simulates local model generation, Secure Aggregation masking, and serialization."""
    # 1. Generate model
    t_start = time.perf_counter()
    rng_local = np.random.default_rng(node_idx)
    parameters = rng_local.uniform(-1.0, 1.0, size=P).astype(np.float32)
    
    # Optional lightweight computation
    parameters = parameters * 1.01
    
    # 2. Secure Aggregation Masking
    t_secagg_start = time.perf_counter()
    mask_sum = np.zeros(P, dtype=np.float32)
    my_name = client_names[node_idx]
    for idx, other_name in enumerate(client_names):
        if idx == node_idx:
            continue
        # Deterministic pair name sorting to align masks between nodes
        pair = sorted([my_name, other_name])
        seed = hash(f"{pair[0]}_{pair[1]}") % (2**32 - 1)
        rng_pair = np.random.default_rng(seed)
        
        # Generate pairwise mask
        mask = rng_pair.standard_normal(P, dtype=np.float32)
        if node_idx < idx:
            mask_sum += mask
        else:
            mask_sum -= mask
            
    masked_parameters = parameters + mask_sum
    t_secagg_end = time.perf_counter()
    secagg_time_ms = (t_secagg_end - t_secagg_start) * 1000.0
    
    # 3. Serialization
    t_ser_start = time.perf_counter()
    serialized_bytes = masked_parameters.tobytes()
    t_ser_end = time.perf_counter()
    ser_time_ms = (t_ser_end - t_ser_start) * 1000.0
    
    return {
        "serialized_bytes": serialized_bytes,
        "secagg_ms": secagg_time_ms,
        "serialization_ms": ser_time_ms
    }


def run_single_model_scale(P: int, num_nodes: int = 5) -> Dict[str, Any]:
    """Runs a single FL round simulation with N nodes for a model parameter count P."""
    logger.info(f"Simulating FL round for model size: {P:,} parameters")
    
    client_names = [f"node_{i}" for i in range(num_nodes)]
    
    t_round_start = time.perf_counter()
    
    # Track baseline memory
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / (1024 * 1024)
    
    # --- Client-Side Operations (Concurrently) ---
    node_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_nodes) as executor:
        futures = {executor.submit(run_node_operations, i, P, client_names): i for i in range(num_nodes)}
        for future in concurrent.futures.as_completed(futures):
            node_results.append(future.result())
            
    # Aggregate client timings
    avg_secagg_ms = sum(r["secagg_ms"] for r in node_results) / num_nodes
    avg_serialization_ms = sum(r["serialization_ms"] for r in node_results) / num_nodes
    
    # --- Server-Side Deserialization ---
    t_deser_start = time.perf_counter()
    deserialized_models = []
    for r in node_results:
        model = np.frombuffer(r["serialized_bytes"], dtype=np.float32)
        deserialized_models.append(model)
    t_deser_end = time.perf_counter()
    deser_time_ms = (t_deser_end - t_deser_start) * 1000.0
    
    # --- Server-Side FedAvg Aggregation ---
    t_fedavg_start = time.perf_counter()
    # FedAvg: element-wise average of models
    aggregated = np.sum(deserialized_models, axis=0) / float(num_nodes)
    t_fedavg_end = time.perf_counter()
    fedavg_time_ms = (t_fedavg_end - t_fedavg_start) * 1000.0
    
    # --- Server-Side Differential Privacy (Laplace noise generation) ---
    t_dp_start = time.perf_counter()
    clip_norm = 1.0
    epsilon = 1.0
    sensitivity = (2.0 * clip_norm) / float(num_nodes)
    scale = sensitivity / epsilon
    
    # Generate and add Laplace noise matching model size
    noise = np.random.laplace(0.0, scale, size=P).astype(np.float32)
    dp_aggregated = aggregated + noise
    t_dp_end = time.perf_counter()
    dp_time_ms = (t_dp_end - t_dp_start) * 1000.0
    
    # Total round timing
    t_round_end = time.perf_counter()
    total_round_ms = (t_round_end - t_round_start) * 1000.0
    
    # Peak memory tracking
    mem_after = process.memory_info().rss / (1024 * 1024)
    peak_mem_mb = max(mem_before, mem_after)
    
    # Serialization metric comprises both serialization and deserialization
    total_serialization_ms = avg_serialization_ms + deser_time_ms
    
    return {
        "parameters": P,
        "fedavg_ms": round(fedavg_time_ms, 3),
        "secagg_ms": round(avg_secagg_ms, 3),
        "dp_noise_ms": round(dp_time_ms, 3),
        "serialization_ms": round(total_serialization_ms, 3),
        "total_round_ms": round(total_round_ms, 3),
        "peak_memory_mb": round(peak_mem_mb, 1)
    }


def generate_figures(results: List[Dict[str, Any]]):
    """Generates four publication-quality figures for the metrics."""
    logger.info("Generating publication-quality scalability graphs...")
    
    import matplotlib.pyplot as plt
    
    params = [r["parameters"] for r in results]
    param_labels = [f"{p:,}" for p in params]
    
    fedavg_times = [r["fedavg_ms"] for r in results]
    secagg_times = [r["secagg_ms"] for r in results]
    dp_times = [r["dp_noise_ms"] for r in results]
    total_times = [r["total_round_ms"] for r in results]
    
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
    
    charts = [
        ("fedavg", fedavg_times, "FedAvg Aggregation Time", "#4F46E5", "fedavg_ms"),
        ("secagg", secagg_times, "Secure Aggregation Time", "#06B6D4", "secagg_ms"),
        ("dp", dp_times, "Differential Privacy Time", "#F59E0B", "dp_noise_ms"),
        ("total", total_times, "Total FL Round Time", "#EF4444", "total_round_ms")
    ]
    
    for filename_key, times, title, color, ylabel in charts:
        fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
        ax.plot(params, times, marker="o", markersize=6, color=color, linewidth=2.0)
        ax.set_title(f"{title} vs. Model Size", fontsize=12, fontweight="bold", pad=12)
        ax.set_xlabel("Model Parameters (Count)", fontsize=10, labelpad=8)
        ax.set_ylabel("Duration (ms)", fontsize=10, labelpad=8)
        
        # Logarithmic scale on X-axis makes spacing of parameters (1k, 10k, 100k, 1M) look uniform
        ax.set_xscale("log")
        ax.set_xticks(params)
        ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
        ax.set_xticklabels(param_labels)
        
        ax.grid(True, linestyle="--", alpha=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#9CA3AF")
        ax.spines["bottom"].set_color("#9CA3AF")
        
        plt.tight_layout()
        plt.savefig(f"figures/model_scalability_{filename_key}.png", dpi=300)
        plt.savefig(f"figures/model_scalability_{filename_key}.svg", format="svg")
        plt.savefig(f"figures/model_scalability_{filename_key}.pdf", format="pdf")
        plt.close()
        
    logger.info("Figures successfully generated in PNG, SVG, and PDF formats.")


def main():
    parser = argparse.ArgumentParser(description="Conclave Model Size Scalability Benchmark")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()
    
    logger.info("Starting Conclave Model Size Scalability Benchmark...")
    set_reproducible_seed(args.seed)
    
    parameter_counts = [1_000, 10_000, 100_000, 1_000_000]
    results = []
    
    for P in tqdm(parameter_counts, desc="Benchmarking Model Size", unit="size"):
        metrics = run_single_model_scale(P, num_nodes=5)
        results.append(metrics)
        logger.info(f"Result for {P:,} parameters: {metrics}")
        
    # Write to CSV
    os.makedirs("results", exist_ok=True)
    csv_file = "results/model_scalability.csv"
    
    keys = ["parameters", "fedavg_ms", "secagg_ms", "dp_noise_ms", "serialization_ms", "total_round_ms", "peak_memory_mb"]
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
