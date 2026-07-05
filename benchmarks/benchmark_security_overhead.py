#!/usr/bin/env python3
"""
conclave.benchmarks.benchmark_security_overhead
─────────────────────────────────────────────────
Privacy & Security Overhead Analysis benchmark.
Quantifies the runtime, communication, and memory overhead of Conclave's
privacy mechanisms (Secure Aggregation and Differential Privacy) over 5 runs.

Saves metrics in a CSV and generates publication-quality figures.
"""

import os
import sys
import time
import csv
import logging
import argparse
import random
import threading
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
logger = logging.getLogger("conclave_security_bench")


def set_reproducible_seed(seed: int):
    """Sets seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    logger.info(f"Reproducible random seed set to: {seed}")


class ResourceMonitor(threading.Thread):
    """Periodically monitors combined CPU and peak RAM utilization of the process tree."""
    def __init__(self, parent_pid: int, interval: float = 0.05):
        super().__init__(daemon=True)
        self.parent_pid = parent_pid
        self.interval = interval
        self.process_baselines: Dict[int, tuple[float, float]] = {}
        self.process_latests: Dict[int, tuple[float, float]] = {}
        self.mem_samples: List[float] = []
        self.stopped = threading.Event()
        self.start_time = 0.0
        self.end_time = 0.0
        self.num_cores = psutil.cpu_count() or 1

    def run(self):
        self.start_time = time.time()
        while not self.stopped.is_set():
            try:
                p = psutil.Process(self.parent_pid)
                children = p.children(recursive=True)
                processes = [p] + children
                
                mem_sum = 0.0
                for proc in processes:
                    try:
                        pid = proc.pid
                        times = proc.cpu_times()
                        curr_user = times.user
                        curr_sys = times.system
                        
                        if pid not in self.process_baselines:
                            self.process_baselines[pid] = (curr_user, curr_sys)
                        self.process_latests[pid] = (curr_user, curr_sys)
                        
                        mem_sum += proc.memory_info().rss / (1024 * 1024)  # MB
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                
                self.mem_samples.append(mem_sum)
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self) -> tuple[float, float]:
        """Stops the monitor and returns (avg_cpu_percent, peak_memory_mb)."""
        self.stopped.set()
        self.end_time = time.time()
        
        # Calculate total accumulated CPU time during monitor run
        total_cpu_time = 0.0
        for pid in self.process_latests:
            if pid in self.process_baselines:
                start_u, start_s = self.process_baselines[pid]
                end_u, end_s = self.process_latests[pid]
                total_cpu_time += (end_u - start_u) + (end_s - start_s)
                
        duration = self.end_time - self.start_time if self.end_time > self.start_time else 0.001
        if duration <= 0:
            duration = 0.001
            
        avg_cpu = (total_cpu_time / (duration * self.num_cores)) * 100.0
        avg_cpu = min(avg_cpu, 100.0)
        
        peak_mem = max(self.mem_samples) if self.mem_samples else 0.0
        return avg_cpu, peak_mem


def run_node_operations(node_idx: int, P: int, client_names: List[str], secagg_enabled: bool) -> Dict[str, Any]:
    """Simulates local model generation, Secure Aggregation masking, and serialization."""
    # 1. Generate model
    rng_local = np.random.default_rng(node_idx)
    parameters = rng_local.uniform(-1.0, 1.0, size=P).astype(np.float32)
    
    # Lightweight local training simulation
    parameters = parameters * 1.01
    
    # 2. Secure Aggregation Masking (if enabled)
    secagg_time_ms = 0.0
    masked_parameters = parameters
    
    if secagg_enabled:
        t_secagg_start = time.perf_counter()
        mask_sum = np.zeros(P, dtype=np.float32)
        my_name = client_names[node_idx]
        for idx, other_name in enumerate(client_names):
            if idx == node_idx:
                continue
            pair = sorted([my_name, other_name])
            seed = hash(f"{pair[0]}_{pair[1]}") % (2**32 - 1)
            rng_pair = np.random.default_rng(seed)
            
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


def run_single_round(P: int, num_nodes: int, secagg_enabled: bool, dp_enabled: bool) -> Dict[str, Any]:
    """Runs a single FL round and returns metrics in milliseconds."""
    client_names = [f"node_{i}" for i in range(num_nodes)]
    
    # Monitor resources for this round
    monitor = ResourceMonitor(os.getpid(), interval=0.01)
    monitor.start()
    
    t_round_start = time.perf_counter()
    
    # --- Client-Side Operations (Concurrently) ---
    node_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_nodes) as executor:
        futures = {executor.submit(run_node_operations, i, P, client_names, secagg_enabled): i for i in range(num_nodes)}
        for future in concurrent.futures.as_completed(futures):
            node_results.append(future.result())
            
    avg_secagg_ms = sum(r["secagg_ms"] for r in node_results) / num_nodes
    avg_serialization_ms = sum(r["serialization_ms"] for r in node_results) / num_nodes
    
    # Calculate payload size (total bytes transmitted by all clients)
    total_payload_bytes = sum(len(r["serialized_bytes"]) for r in node_results)
    
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
    aggregated = np.sum(deserialized_models, axis=0) / float(num_nodes)
    t_fedavg_end = time.perf_counter()
    fedavg_time_ms = (t_fedavg_end - t_fedavg_start) * 1000.0
    
    # --- Server-Side Differential Privacy (Laplace noise generation) ---
    dp_time_ms = 0.0
    if dp_enabled:
        t_dp_start = time.perf_counter()
        clip_norm = 1.0
        epsilon = 1.0
        sensitivity = (2.0 * clip_norm) / float(num_nodes)
        scale = sensitivity / epsilon
        
        noise = np.random.laplace(0.0, scale, size=P).astype(np.float32)
        dp_aggregated = aggregated + noise
        t_dp_end = time.perf_counter()
        dp_time_ms = (t_dp_end - t_dp_start) * 1000.0
        
    t_round_end = time.perf_counter()
    total_round_ms = (t_round_end - t_round_start) * 1000.0
    
    # Stop monitoring
    avg_cpu, peak_mem = monitor.stop()
    monitor.join(timeout=1.0)
    
    return {
        "total_round_ms": total_round_ms,
        "aggregation_ms": fedavg_time_ms,
        "secagg_ms": avg_secagg_ms,
        "dp_ms": dp_time_ms,
        "payload_bytes": total_payload_bytes,
        "cpu_percent": avg_cpu,
        "peak_memory_mb": peak_mem
    }


def generate_figures(results: List[Dict[str, Any]]):
    """Generates four publication-quality overhead figures using Matplotlib."""
    logger.info("Generating publication-quality overhead graphs...")
    
    import matplotlib.pyplot as plt
    
    configs = [r["configuration"] for r in results]
    round_times = [r["total_round_ms"] for r in results]
    agg_times = [r["aggregation_ms"] for r in results]
    payloads = [r["payload_bytes"] for r in results]
    cpu_usages = [r["cpu_percent"] for r in results]
    
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
    
    # Helper to style bar charts
    def style_ax(ax, title, ylabel):
        ax.set_title(title, fontsize=12, fontweight="bold", pad=12)
        ax.set_ylabel(ylabel, fontsize=10, labelpad=8)
        ax.set_xlabel("Security Configuration", fontsize=10, labelpad=8)
        ax.grid(True, axis="y", linestyle="--", alpha=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#9CA3AF")
        ax.spines["bottom"].set_color("#9CA3AF")
        
    # --- Figure 1: Total FL Round Time ---
    fig, ax = plt.subplots(figsize=(6.5, 4.5), dpi=300)
    bars = ax.bar(configs, round_times, color="#EF4444", width=0.5, edgecolor="none")
    style_ax(ax, "Total FL Round Duration by Config", "Time (ms)")
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f"{height:.2f}ms",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig("figures/security_overhead_total.png", dpi=300)
    plt.savefig("figures/security_overhead_total.svg", format="svg")
    plt.savefig("figures/security_overhead_total.pdf", format="pdf")
    plt.close()
    
    # --- Figure 2: Aggregation Time ---
    fig, ax = plt.subplots(figsize=(6.5, 4.5), dpi=300)
    bars = ax.bar(configs, agg_times, color="#4F46E5", width=0.5, edgecolor="none")
    style_ax(ax, "FedAvg Aggregation Time by Config", "Time (ms)")
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f"{height:.3f}ms",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig("figures/security_overhead_aggregation.png", dpi=300)
    plt.savefig("figures/security_overhead_aggregation.svg", format="svg")
    plt.savefig("figures/security_overhead_aggregation.pdf", format="pdf")
    plt.close()
    
    # --- Figure 3: Payload Size ---
    fig, ax = plt.subplots(figsize=(6.5, 4.5), dpi=300)
    bars = ax.bar(configs, [p / 1024.0 for p in payloads], color="#06B6D4", width=0.5, edgecolor="none")
    style_ax(ax, "Total Communication Payload by Config", "Payload Size (KB)")
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f"{height:.1f} KB",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig("figures/security_overhead_payload.png", dpi=300)
    plt.savefig("figures/security_overhead_payload.svg", format="svg")
    plt.savefig("figures/security_overhead_payload.pdf", format="pdf")
    plt.close()
    
    # --- Figure 4: CPU Usage ---
    fig, ax = plt.subplots(figsize=(6.5, 4.5), dpi=300)
    bars = ax.bar(configs, cpu_usages, color="#F59E0B", width=0.5, edgecolor="none")
    style_ax(ax, "Average CPU Utilization by Config", "CPU Usage (%)")
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f"{height:.2f}%",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig("figures/security_overhead_cpu.png", dpi=300)
    plt.savefig("figures/security_overhead_cpu.svg", format="svg")
    plt.savefig("figures/security_overhead_cpu.pdf", format="pdf")
    plt.close()
    
    logger.info("Figures successfully generated in PNG, SVG, and PDF formats.")


def main():
    parser = argparse.ArgumentParser(description="Conclave Privacy & Security Overhead Benchmark")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()
    
    logger.info("Starting Conclave Privacy & Security Overhead Benchmark...")
    set_reproducible_seed(args.seed)
    
    P = 100_000
    num_nodes = 5
    repetitions = 5
    
    configs = [
        {"name": "A", "desc": "Plain FedAvg", "secagg": False, "dp": False},
        {"name": "B", "desc": "FedAvg + SecAgg", "secagg": True, "dp": False},
        {"name": "C", "desc": "FedAvg + DP", "secagg": False, "dp": True},
        {"name": "D", "desc": "FedAvg + SecAgg + DP", "secagg": True, "dp": True}
    ]
    
    results = []
    
    # Loop over configurations
    for conf in tqdm(configs, desc="Benchmarking Security Configs", unit="config"):
        logger.info(f"Evaluating Configuration {conf['name']}: {conf['desc']} over {repetitions} runs...")
        
        rep_metrics = []
        for r in range(repetitions):
            metrics = run_single_round(P, num_nodes, conf["secagg"], conf["dp"])
            rep_metrics.append(metrics)
            time.sleep(0.1)  # Cooldown
            
        # Compute average metrics across repetitions
        avg_metrics = {
            "configuration": conf["name"],
            "total_round_ms": round(sum(m["total_round_ms"] for m in rep_metrics) / repetitions, 3),
            "aggregation_ms": round(sum(m["aggregation_ms"] for m in rep_metrics) / repetitions, 3),
            "secagg_ms": round(sum(m["secagg_ms"] for m in rep_metrics) / repetitions, 3),
            "dp_ms": round(sum(m["dp_ms"] for m in rep_metrics) / repetitions, 3),
            "payload_bytes": rep_metrics[0]["payload_bytes"],  # Payload size is identical across runs
            "cpu_percent": round(sum(m["cpu_percent"] for m in rep_metrics) / repetitions, 2),
            "peak_memory_mb": round(max(m["peak_memory_mb"] for m in rep_metrics), 1)  # Peak RSS over all runs
        }
        results.append(avg_metrics)
        logger.info(f"Avg Result for Configuration {conf['name']}: {avg_metrics}")
        
    # Write to CSV
    os.makedirs("results", exist_ok=True)
    csv_file = "results/security_overhead.csv"
    
    keys = ["configuration", "total_round_ms", "aggregation_ms", "secagg_ms", "dp_ms", "payload_bytes", "cpu_percent", "peak_memory_mb"]
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
