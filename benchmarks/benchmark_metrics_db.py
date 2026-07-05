#!/usr/bin/env python3
"""
conclave.benchmarks.benchmark_metrics_db
──────────────────────────────────────────
Metrics Database Ingestion Throughput benchmark.
Evaluates SQLite write performance, latency, and reliability under concurrent
write workloads simulating multiple hospital nodes uploading resource metrics.

Saves metrics in a CSV and generates publication-quality figures.
"""

import os
import sys
import time
import csv
import logging
import argparse
import random
import sqlite3
import threading
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
logger = logging.getLogger("conclave_metrics_db_bench")


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


def init_db(db_path: str):
    """Creates schema for metrics logging and sets WAL mode."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS node_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                node_id TEXT,
                cpu REAL,
                ram REAL,
                gpu REAL,
                disk REAL,
                network_sent INTEGER,
                network_received INTEGER,
                heartbeat_status TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def writer_thread_task(
    thread_idx: int,
    db_path: str,
    num_inserts: int,
    success_list: List[int],
    fail_list: List[int],
    latencies: List[float]
):
    """Executes sequential individual inserts, simulating node heartbeat uploads."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        # Pre-configure connections for concurrent performance
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        
        node_id = f"node_thread_{thread_idx}"
        
        for i in range(num_inserts):
            t_start = time.perf_counter()
            timestamp = datetime.now().isoformat()
            cpu_val = random.uniform(0.0, 100.0)
            ram_val = random.uniform(10.0, 95.0)
            gpu_val = random.uniform(0.0, 100.0)
            disk_val = random.uniform(20.0, 85.0)
            net_sent = random.randint(100, 100000)
            net_rec = random.randint(100, 100000)
            status = "Online"
            
            try:
                conn.execute(
                    """
                    INSERT INTO node_metrics (
                        timestamp, node_id, cpu, ram, gpu, disk, network_sent, network_received, heartbeat_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp, node_id, cpu_val, ram_val, gpu_val, disk_val, net_sent, net_rec, status)
                )
                conn.commit()
                t_end = time.perf_counter()
                
                success_list.append(1)
                latencies.append((t_end - t_start) * 1000.0)
            except sqlite3.OperationalError as e:
                # Capture write locking errors
                fail_list.append(1)
    finally:
        conn.close()


def run_single_db_benchmark(T: int, rep: int) -> Dict[str, Any]:
    """Runs database writes under thread count T, validating final integrity."""
    os.makedirs("results", exist_ok=True)
    db_path = f"results/metrics_bench_T{T}_rep{rep}.db"
    
    # Ensure a fresh database
    for ext in ["", "-wal", "-shm", "-journal"]:
        file_path = f"{db_path}{ext}"
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
                
    init_db(db_path)
    
    num_inserts = 1000
    success_list: List[int] = []
    fail_list: List[int] = []
    latencies: List[float] = []
    
    # Start resource monitor
    monitor = ResourceMonitor(os.getpid(), interval=0.02)
    monitor.start()
    
    t_start = time.perf_counter()
    
    # Spawn and start concurrent writer threads
    threads = []
    for idx in range(T):
        t = threading.Thread(
            target=writer_thread_task,
            args=(idx, db_path, num_inserts, success_list, fail_list, latencies)
        )
        threads.append(t)
        
    for t in threads:
        t.start()
        
    for t in threads:
        t.join()
        
    t_end = time.perf_counter()
    execution_time_ms = (t_end - t_start) * 1000.0
    
    avg_cpu, peak_mem = monitor.stop()
    monitor.join(timeout=1.0)
    
    successful_writes = len(success_list)
    failed_writes = len(fail_list)
    total_operations = T * num_inserts
    
    avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0
    writes_per_second = successful_writes / (t_end - t_start) if (t_end - t_start) > 0 else 0
    
    # Database Integrity Validation
    validation_status = "Valid"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verify row count
        cursor.execute("SELECT COUNT(*) FROM node_metrics")
        actual_rows = cursor.fetchone()[0]
        if actual_rows != successful_writes:
            validation_status = "Row count mismatch"
            logger.warning(f"Integrity check failed: row count mismatch. Expected: {successful_writes}, Found: {actual_rows}")
            
        # Verify unique IDs
        cursor.execute("SELECT COUNT(DISTINCT id) FROM node_metrics")
        distinct_ids = cursor.fetchone()[0]
        if distinct_ids != actual_rows:
            validation_status = "Duplicate IDs found"
            logger.warning("Integrity check failed: duplicate IDs found.")
            
        conn.close()
    except Exception as e:
        validation_status = f"Read error: {e}"
        logger.error(f"Integrity check failed: {e}")
        
    # Capture database file size (include WAL files if active)
    db_size_bytes = 0
    for ext in ["", "-wal", "-shm"]:
        fp = f"{db_path}{ext}"
        if os.path.exists(fp):
            db_size_bytes += os.path.getsize(fp)
    db_size_mb = db_size_bytes / (1024 * 1024)
    
    # Clean up database files post verification
    for ext in ["", "-wal", "-shm", "-journal"]:
        file_path = f"{db_path}{ext}"
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
                
    return {
        "writer_threads": T,
        "total_operations": total_operations,
        "successful_writes": successful_writes,
        "failed_writes": failed_writes,
        "execution_time_ms": execution_time_ms,
        "average_latency_ms": avg_latency_ms,
        "writes_per_second": writes_per_second,
        "database_size_mb": db_size_mb,
        "peak_memory_mb": peak_mem,
        "cpu_percent": avg_cpu,
        "integrity": validation_status
    }


def generate_figures(results: List[Dict[str, Any]]):
    """Generates four publication-quality overhead figures using Matplotlib."""
    logger.info("Generating publication-quality metrics database graphs...")
    
    import matplotlib.pyplot as plt
    
    threads = [r["writer_threads"] for r in results]
    throughput = [r["writes_per_second"] for r in results]
    latency = [r["average_latency_ms"] for r in results]
    size = [r["database_size_mb"] for r in results]
    cpu = [r["cpu_percent"] for r in results]
    
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
        ax.set_xlabel("Writer Threads (Count)", fontsize=10, labelpad=8)
        ax.set_ylabel(ylabel, fontsize=10, labelpad=8)
        ax.set_xscale("log")
        ax.set_xticks(threads)
        ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
        ax.set_xticklabels([str(t) for t in threads])
        ax.grid(True, linestyle="--", alpha=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#9CA3AF")
        ax.spines["bottom"].set_color("#9CA3AF")

    # --- Figure 1: Database Throughput ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(threads, throughput, marker="o", markersize=6, color="#4F46E5", linewidth=2.0)
    style_ax(ax, "Ingestion Throughput vs. Threads", "Throughput (writes/sec)")
    plt.tight_layout()
    plt.savefig("figures/metrics_db_throughput.png", dpi=300)
    plt.savefig("figures/metrics_db_throughput.svg", format="svg")
    plt.savefig("figures/metrics_db_throughput.pdf", format="pdf")
    plt.close()
    
    # --- Figure 2: Average Write Latency ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(threads, latency, marker="s", markersize=6, color="#EF4444", linewidth=2.0)
    style_ax(ax, "Write Latency vs. Threads", "Average Latency (ms)")
    plt.tight_layout()
    plt.savefig("figures/metrics_db_latency.png", dpi=300)
    plt.savefig("figures/metrics_db_latency.svg", format="svg")
    plt.savefig("figures/metrics_db_latency.pdf", format="pdf")
    plt.close()
    
    # --- Figure 3: Database Size ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(threads, size, marker="^", markersize=6, color="#06B6D4", linewidth=2.0)
    style_ax(ax, "Database File Size vs. Threads", "File Size (MB)")
    plt.tight_layout()
    plt.savefig("figures/metrics_db_size.png", dpi=300)
    plt.savefig("figures/metrics_db_size.svg", format="svg")
    plt.savefig("figures/metrics_db_size.pdf", format="pdf")
    plt.close()
    
    # --- Figure 4: CPU Utilization ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(threads, cpu, marker="d", markersize=6, color="#F59E0B", linewidth=2.0)
    style_ax(ax, "CPU Utilization vs. Threads", "CPU Usage (%)")
    plt.tight_layout()
    plt.savefig("figures/metrics_db_cpu.png", dpi=300)
    plt.savefig("figures/metrics_db_cpu.svg", format="svg")
    plt.savefig("figures/metrics_db_cpu.pdf", format="pdf")
    plt.close()
    
    logger.info("Metrics database graphs successfully generated in PNG, SVG, and PDF formats.")


def main():
    parser = argparse.ArgumentParser(description="Conclave Metrics Database Ingestion Throughput Benchmark")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()
    
    logger.info("Starting Conclave Metrics Database Ingestion Throughput Benchmark...")
    set_reproducible_seed(args.seed)
    
    thread_counts = [1, 5, 10, 20, 50]
    repetitions = 5
    results = []
    
    for T in tqdm(thread_counts, desc="Benchmarking Writer Threads", unit="scale"):
        logger.info(f"Evaluating concurrent write load: {T} threads over {repetitions} runs...")
        
        rep_metrics = []
        for r in range(repetitions):
            metrics = run_single_db_benchmark(T, r)
            rep_metrics.append(metrics)
            time.sleep(0.1)  # Cooldown
            
        # Compute average metrics across repetitions
        avg_metrics = {
            "writer_threads": T,
            "total_operations": T * 1000,
            "successful_writes": round(sum(m["successful_writes"] for m in rep_metrics) / repetitions),
            "failed_writes": round(sum(m["failed_writes"] for m in rep_metrics) / repetitions),
            "execution_time_ms": round(sum(m["execution_time_ms"] for m in rep_metrics) / repetitions, 3),
            "average_latency_ms": round(sum(m["average_latency_ms"] for m in rep_metrics) / repetitions, 3),
            "writes_per_second": round(sum(m["writes_per_second"] for m in rep_metrics) / repetitions, 1),
            "database_size_mb": round(sum(m["database_size_mb"] for m in rep_metrics) / repetitions, 2),
            "peak_memory_mb": round(max(m["peak_memory_mb"] for m in rep_metrics), 1),
            "cpu_percent": round(sum(m["cpu_percent"] for m in rep_metrics) / repetitions, 2)
        }
        results.append(avg_metrics)
        logger.info(f"Avg Result for {T} threads: {avg_metrics}")
        
    # Write to CSV
    os.makedirs("results", exist_ok=True)
    csv_file = "results/metrics_db_benchmark.csv"
    
    keys = ["writer_threads", "total_operations", "successful_writes", "failed_writes", "execution_time_ms", "average_latency_ms", "writes_per_second", "database_size_mb", "peak_memory_mb", "cpu_percent"]
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
