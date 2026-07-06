#!/usr/bin/env python3
"""
conclave.benchmarks.benchmark_end_to_end
─────────────────────────────────────────
End-to-End Federated Learning System Performance benchmark.
Evaluates overall Conclave performance (orchestration, heartbeats,
coordinator, SecAgg, DP, audit logging, and metrics collection)
across configurations (3, 5, 10 nodes) over 5 rounds.

Saves metrics in a CSV and generates publication-quality figures.
"""

import os
import sys
import time
import csv
import logging
import random
import socket
import threading
import subprocess
import argparse
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

import numpy as np
import requests
import psutil
import jwt
from tqdm import tqdm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("conclave_e2e_bench")

# Database and port configurations
DB_FILE = "conclave_scalability_bench.db"
METRICS_DB_FILE = "conclave_bench_metrics.db"
FLOWER_PORT = 8080


def wait_for_port_free(port: int, timeout: float = 15.0) -> bool:
    """Blocks until the specified port is released on localhost."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                pass
        time.sleep(0.5)
    return False


def set_reproducible_seed(seed: int):
    """Sets seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    logger.info(f"Reproducible random seed set to: {seed}")


def init_wal_dbs():
    """Pre-initializes the SQLite database files in WAL mode to handle concurrency."""
    for db in [DB_FILE, METRICS_DB_FILE]:
        conn = sqlite3.connect(db)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        finally:
            conn.close()


def cleanup_dbs():
    """Deletes temporary database files and journal/WAL files."""
    for db in [DB_FILE, METRICS_DB_FILE]:
        for ext in ["", "-wal", "-shm", "-journal"]:
            file_path = f"{db}{ext}"
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.warning(f"Could not remove {file_path}: {e}")


class ResourceMonitor(threading.Thread):
    """Periodically monitors combined CPU and peak RAM utilization of the process tree."""
    def __init__(self, parent_pid: int, interval: float = 0.2):
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


class SimulatedNode:
    """Manages a simulated node, its RSA keys, heartbeat loop, and Flower client thread."""
    def __init__(self, node_index: int, hostname: str, server_url: str, private_key, public_key_pem: str):
        self.node_index = node_index
        self.hostname = hostname
        self.server_url = server_url
        self.private_key = private_key
        self.public_key_pem = public_key_pem
        self.node_id: Optional[str] = None
        
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.flower_thread: Optional[threading.Thread] = None
        self.stop_heartbeat = threading.Event()
        self.heartbeat_latencies: List[float] = []
        self.heartbeat_count = 0
        self.training_started = False
        self.training_completed = False

    def register_and_approve(self, org_id: str) -> bool:
        """Registers the node spec and public key, then approves the registration."""
        register_payload = {
            "organization_id": org_id,
            "hostname": self.hostname,
            "node_name": f"Simulated Node {self.node_index}",
            "os_name": "Linux" if sys.platform != "win32" else "Windows",
            "os_version": "Bench-6.0",
            "architecture": "x86_64",
            "cpu_model": "Simulated CPU",
            "cpu_cores": 2,
            "ram_gb": 8.0,
            "gpu_available": "No",
            "public_key": self.public_key_pem
        }
        
        try:
            # 1. Register
            r = requests.post(f"{self.server_url}/nodes/register", json=register_payload, timeout=5)
            if r.status_code not in (200, 201):
                logger.error(f"Node register failed for {self.hostname}: {r.text}")
                return False
            data = r.json()
            self.node_id = data["id"]
            
            # 2. Approve
            r_app = requests.post(f"{self.server_url}/nodes/approve/{self.node_id}", timeout=5)
            if r_app.status_code != 200:
                logger.error(f"Node approve failed for {self.hostname}: {r_app.text}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Exception registering/approving node {self.hostname}: {e}")
            return False

    def start_heartbeat_loop(self):
        """Spawns the heartbeat reporting thread."""
        self.heartbeat_thread = threading.Thread(target=self._run_heartbeat, daemon=True)
        self.heartbeat_thread.start()

    def _run_heartbeat(self):
        """Periodic heartbeat loop with cryptographic signatures."""
        while not self.stop_heartbeat.is_set():
            now_ts = int(time.time())
            token = jwt.encode(
                {"sub": self.node_id, "exp": now_ts + 120, "iat": now_ts},
                self.private_key,
                algorithm="RS256"
            )
            
            headers = {"X-Node-Token": token}
            payload = {
                "cpu_utilization": round(random.uniform(5.0, 15.0), 1),
                "ram_utilization": round(random.uniform(20.0, 45.0), 1)
            }
            
            t0 = time.time()
            try:
                r = requests.post(
                    f"{self.server_url}/nodes/heartbeat/{self.node_id}",
                    json=payload,
                    headers=headers,
                    timeout=5
                )
                latency_ms = (time.time() - t0) * 1000.0
                if r.status_code == 200:
                    self.heartbeat_latencies.append(latency_ms)
                    self.heartbeat_count += 1
                    resp_data = r.json()
                    
                    active_task = resp_data.get("active_task")
                    if active_task and not self.training_started:
                        self.training_started = True
                        self._spawn_flower_client(active_task)
                else:
                    logger.warning(f"Heartbeat failed for {self.hostname} ({r.status_code}): {r.text}")
            except Exception as e:
                logger.warning(f"Heartbeat network error for {self.hostname}: {e}")
                
            time.sleep(1.0)

    def _spawn_flower_client(self, active_task: dict):
        """Starts a background Flower client thread connecting to the server."""
        self.flower_thread = threading.Thread(
            target=self._run_flower_client,
            args=(active_task,),
            daemon=True
        )
        self.flower_thread.start()

    def _run_flower_client(self, active_task: dict):
        """Flower client thread execution."""
        server_address = active_task["server_address"]
        privacy_cfg = active_task.get("privacy", {})
        
        try:
            import flwr as fl
            from conclave.integrations.flower.orchestrator import SimpleFlowerClient
            
            client = SimpleFlowerClient(self.hostname, privacy_config=privacy_cfg)
            fl.client.start_numpy_client(server_address=server_address, client=client)
            self.training_completed = True
            logger.info(f"Node {self.hostname} successfully completed training task.")
        except Exception as e:
            logger.error(f"Flower client error on node {self.hostname}: {e}")
        finally:
            self.stop_heartbeat.set()


def run_single_benchmark_iteration(node_count: int, seed: int, run_idx: int) -> dict:
    """Runs the complete end-to-end cycle for node_count nodes and returns metrics."""
    logger.info(f"\n==========================================")
    logger.info(f"Starting E2E Run: {node_count} Nodes (Iteration {run_idx})")
    logger.info(f"==========================================")
    
    set_reproducible_seed(seed)
    cleanup_dbs()
    init_wal_dbs()
    
    # Clean/clear aggregation times file from previous runs
    agg_times_file = "results/aggregation_times.txt"
    if os.path.exists(agg_times_file):
        try:
            os.remove(agg_times_file)
        except Exception:
            pass
            
    # Prevent port collisions across runs
    server_port = 8000 + node_count + run_idx
    server_url = f"http://127.0.0.1:{server_port}"
    
    # 1. Start FastAPI Server
    server_env = os.environ.copy()
    server_env["CONCLAVE_DB_FILE"] = DB_FILE
    server_env["CONCLAVE_METRICS_DB_FILE"] = METRICS_DB_FILE
    server_env["BYPASS_AUTH"] = "true"
    server_env["TESTING"] = "true"
    
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "conclave.server.main:app", "--host", "127.0.0.1", "--port", str(server_port)],
        env=server_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for the FastAPI server to bind and start
    time.sleep(3.0)
    
    nodes: List[SimulatedNode] = []
    resource_monitor = None
    training_duration = 0.0
    iter_start_time = time.time()
    session_name = f"session_e2e_{node_count}_{run_idx}"
    
    try:
        # 2. Register Organizations and Clients (Secure Aggregation requires >= 3 clients)
        org_ids = []
        client_names = ["test_org_1", "test_org_2", "test_org_3"]
        for name in client_names:
            # Register Organization
            r_org = requests.post(
                f"{server_url}/organizations/create",
                json={"name": name, "organization_type": "Hospital", "description": f"Benchmark Org {name}"}
            )
            if r_org.status_code != 200:
                raise RuntimeError(f"Failed to create organization {name}: {r_org.text}")
            org_id = r_org.json()["id"]
            org_ids.append(org_id)

            # Register Governance Client
            r_client = requests.post(
                f"{server_url}/clients/register",
                json={"name": name, "client_type": "Governance Client"}
            )
            if r_client.status_code != 200:
                raise RuntimeError(f"Failed to register governance client {name}: {r_client.text}")
        
        # 3. Grant Dataset Consents
        for name in client_names:
            r_consent = requests.post(
                f"{server_url}/consents/grant",
                json={"client_name": name, "dataset_name": "test_dataset"}
            )
            if r_consent.status_code != 200:
                raise RuntimeError(f"Failed to grant client consent for {name}: {r_consent.text}")
            
        # 4. Pre-seed Policy (Enable both SecAgg and DP)
        r_pol = requests.post(
            f"{server_url}/policies/create",
            json={
                "name": "e2e_policy",
                "description": "E2E Benchmark Policy",
                "secagg_enabled": True,
                "dp_enabled": True,
                "dp_epsilon": 1.0,
                "dp_delta": 1e-5
            }
        )
        if r_pol.status_code != 200:
            raise RuntimeError(f"Failed to create policy: {r_pol.text}")
            
        # 5. Generate keys & register nodes distributed among organizations
        logger.info(f"Generating RSA key pairs and registering {node_count} nodes...")
        for i in range(1, node_count + 1):
            org_idx = (i - 1) % len(client_names)
            org_name = client_names[org_idx]
            org_id = org_ids[org_idx]
            
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pub_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode()
            
            node = SimulatedNode(
                node_index=i,
                hostname=f"node_e2e_{node_count}_{run_idx}_{i}",
                server_url=server_url,
                private_key=private_key,
                public_key_pem=pub_pem
            )
            if not node.register_and_approve(org_id):
                raise RuntimeError(f"Could not register/approve simulated node {i} under org {org_name}")
            nodes.append(node)
            
        # 6. Start Resource Monitor
        resource_monitor = ResourceMonitor(os.getpid(), interval=0.1)
        resource_monitor.start()
        
        # 7. Start Heartbeat Loops
        logger.info("Activating heartbeat loop for nodes...")
        for node in nodes:
            node.start_heartbeat_loop()
            
        # 8. Wait for all nodes to report Online
        logger.info("Waiting for all nodes to report Online status...")
        all_online = False
        for _ in range(60):
            try:
                r = requests.get(f"{server_url}/nodes/list")
                if r.status_code == 200:
                    online_count = sum(1 for n in r.json() if n["status"] == "Online")
                    if online_count >= node_count:
                        all_online = True
                        break
            except Exception:
                pass
            time.sleep(0.5)
            
        if not all_online:
            raise RuntimeError("Nodes failed to reach Online status in time.")
            
        # 9. Create training session (request 5 rounds in description)
        logger.info("All nodes are Online. Creating and launching training session...")
        r_session = requests.post(
            f"{server_url}/trainings/create",
            json={
                "name": session_name,
                "participating_clients": ["test_org_1", "test_org_2", "test_org_3"],
                "assigned_policy": "e2e_policy",
                "dataset_name": "test_dataset",
                "description": "E2E Performance run with rounds=5",
                "priority": "Medium"
            }
        )
        if r_session.status_code != 200:
            raise RuntimeError(f"Failed to create training session: {r_session.text}")
            
        # 10. Start training session (blocks until completed)
        training_start = time.time()
        r_start = requests.post(f"{server_url}/trainings/start/{session_name}", timeout=180)
        training_duration = time.time() - training_start
        
        if r_start.status_code != 200:
            raise RuntimeError(f"Training session run failed: {r_start.text}")
            
        # Verify execution status
        r_verify = requests.get(f"{server_url}/trainings/show/{session_name}")
        if r_verify.status_code == 200:
            session_status = r_verify.json().get("status")
            if session_status != "Completed":
                raise RuntimeError(f"System validation failed: training status is '{session_status}', expected 'Completed'.")
        else:
            raise RuntimeError(f"Could not retrieve training status: {r_verify.text}")
            
        logger.info(f"Training session complete! Duration: {training_duration:.2f} seconds.")
        
        # Wait for heartbeats loop to cleanly exit
        time.sleep(1.0)
        
    except Exception as e:
        logger.error(f"Benchmark iteration failed with error: {e}")
        for node in nodes:
            node.stop_heartbeat.set()
        raise e
        
    finally:
        # Stop resource monitoring
        avg_cpu, peak_mem = 0.0, 0.0
        if resource_monitor:
            avg_cpu, peak_mem = resource_monitor.stop()
            resource_monitor.join(timeout=2)
            
        # Explicitly stop heartbeat loops
        for node in nodes:
            node.stop_heartbeat.set()
            if node.heartbeat_thread:
                node.heartbeat_thread.join(timeout=2)
            if node.flower_thread:
                node.flower_thread.join(timeout=2)
                
        # Calculate total execution runtime
        iter_runtime = time.time() - iter_start_time
        
        # Kill Conclave Server Process
        logger.info("Shutting down Conclave server process...")
        try:
            server_proc.terminate()
            server_proc.wait(timeout=5)
        except Exception:
            try:
                server_proc.kill()
            except Exception:
                pass
                
        # Wait for Flower server port to release
        logger.info("Waiting for Flower server port (8080) to be fully released...")
        if not wait_for_port_free(FLOWER_PORT, timeout=15):
            logger.warning(f"Flower server port {FLOWER_PORT} was not released in time.")
            
    # --- Post-Teardown Log and Metrics Counting ---
    audit_entries_count = 0
    metrics_records_count = 0
    
    # Read database logs directly
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_events")
        audit_entries_count = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.error(f"Failed to read audit events count: {e}")
        
    try:
        conn = sqlite3.connect(METRICS_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM node_metrics")
        metrics_records_count = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.error(f"Failed to read node metrics count: {e}")
        
    # Read aggregation times
    agg_times = []
    if os.path.exists(agg_times_file):
        try:
            with open(agg_times_file, "r") as f_agg:
                for line in f_agg:
                    parts = line.strip().split(",")
                    if len(parts) == 3:
                        s_id, rnd, t_ms = parts
                        # We don't have the session UUID locally, so match all aggregation entries in the file
                        agg_times.append(float(t_ms))
        except Exception as e:
            logger.error(f"Failed to read aggregation times file: {e}")
            
    avg_agg_ms = sum(agg_times) / len(agg_times) if agg_times else 0.0
    
    # Aggregate latencies and heartbeats
    all_latencies = []
    total_hb = 0
    for node in nodes:
        all_latencies.extend(node.heartbeat_latencies)
        total_hb += node.heartbeat_count
        
    avg_hb_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
    avg_round_time = training_duration / 5.0  # 5 rounds
    
    # Clean up database files post iteration to prevent space buildup
    cleanup_dbs()
    
    # System Validation asserts
    if audit_entries_count == 0:
        logger.warning("System Validation Warning: 0 audit events recorded.")
    if metrics_records_count == 0:
        logger.warning("System Validation Warning: 0 metrics records recorded.")
    for node in nodes:
        if not node.training_completed:
            raise RuntimeError(f"System Validation Failed: Node '{node.hostname}' did not complete training round.")
            
    return {
        "nodes": node_count,
        "rounds": 5,
        "total_runtime_sec": iter_runtime,
        "avg_round_sec": avg_round_time,
        "aggregation_ms": avg_agg_ms,
        "heartbeat_ms": avg_hb_latency,
        "heartbeats": total_hb,
        "audit_entries": audit_entries_count,
        "metrics_records": metrics_records_count,
        "cpu_percent": avg_cpu,
        "peak_memory_mb": peak_mem
    }


def generate_figures(results: List[Dict[str, Any]]):
    """Generates five publication-quality figures using Matplotlib."""
    logger.info("Generating publication-quality scalability graphs...")
    
    import matplotlib.pyplot as plt
    
    nodes = [r["nodes"] for r in results]
    runtimes = [r["total_runtime_sec"] for r in results]
    round_durations = [r["avg_round_sec"] for r in results]
    hb_latencies = [r["heartbeat_ms"] for r in results]
    cpu_usages = [r["cpu_percent"] for r in results]
    peak_memories = [r["peak_memory_mb"] for r in results]
    
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
        ax.set_xlabel("Number of Simulated Nodes", fontsize=10, labelpad=8)
        ax.set_ylabel(ylabel, fontsize=10, labelpad=8)
        ax.set_xticks(nodes)
        ax.grid(True, linestyle="--", alpha=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#9CA3AF")
        ax.spines["bottom"].set_color("#9CA3AF")
        
    # 1. Nodes vs Total Runtime
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(nodes, runtimes, marker="o", markersize=6, color="#4F46E5", linewidth=2.0)
    style_ax(ax, "Total Runtime vs. Node Scale", "Execution Time (sec)")
    plt.tight_layout()
    plt.savefig("figures/end_to_end_total_runtime.png", dpi=300)
    plt.savefig("figures/end_to_end_total_runtime.svg", format="svg")
    plt.savefig("figures/end_to_end_total_runtime.pdf", format="pdf")
    plt.close()
    
    # 2. Nodes vs Avg Round Duration
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(nodes, round_durations, marker="s", markersize=6, color="#EF4444", linewidth=2.0)
    style_ax(ax, "Average Round Duration vs. Node Scale", "Round Duration (sec)")
    plt.tight_layout()
    plt.savefig("figures/end_to_end_round_duration.png", dpi=300)
    plt.savefig("figures/end_to_end_round_duration.svg", format="svg")
    plt.savefig("figures/end_to_end_round_duration.pdf", format="pdf")
    plt.close()
    
    # 3. Nodes vs Heartbeat Latency
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(nodes, hb_latencies, marker="^", markersize=6, color="#06B6D4", linewidth=2.0)
    style_ax(ax, "Heartbeat Latency vs. Node Scale", "Latency (ms)")
    plt.tight_layout()
    plt.savefig("figures/end_to_end_heartbeat_latency.png", dpi=300)
    plt.savefig("figures/end_to_end_heartbeat_latency.svg", format="svg")
    plt.savefig("figures/end_to_end_heartbeat_latency.pdf", format="pdf")
    plt.close()
    
    # 4. Nodes vs CPU Usage
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(nodes, cpu_usages, marker="d", markersize=6, color="#F59E0B", linewidth=2.0)
    style_ax(ax, "CPU Utilization vs. Node Scale", "CPU Usage (%)")
    plt.tight_layout()
    plt.savefig("figures/end_to_end_cpu_usage.png", dpi=300)
    plt.savefig("figures/end_to_end_cpu_usage.svg", format="svg")
    plt.savefig("figures/end_to_end_cpu_usage.pdf", format="pdf")
    plt.close()
    
    # 5. Nodes vs Peak Memory
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(nodes, peak_memories, marker="p", markersize=6, color="#10B981", linewidth=2.0)
    style_ax(ax, "Peak Memory Footprint vs. Node Scale", "Peak Memory (MB)")
    plt.tight_layout()
    plt.savefig("figures/end_to_end_memory_usage.png", dpi=300)
    plt.savefig("figures/end_to_end_memory_usage.svg", format="svg")
    plt.savefig("figures/end_to_end_memory_usage.pdf", format="pdf")
    plt.close()
    
    logger.info("Figures successfully generated in PNG, SVG, and PDF formats.")


def main():
    parser = argparse.ArgumentParser(description="Conclave End-to-End FL System Performance Benchmark")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()
    
    logger.info("Starting Conclave End-to-End FL Performance Benchmark...")
    
    target_nodes = [3, 5, 10]
    repetitions = 3
    results = []
    
    # Process bar across configurations
    for node_count in tqdm(target_nodes, desc="Benchmarking Node Scale", unit="config"):
        try:
            rep_metrics = []
            for r in range(1, repetitions + 1):
                metrics = run_single_benchmark_iteration(node_count, args.seed, r)
                rep_metrics.append(metrics)
                time.sleep(2.0)  # Cooldown between runs
                
            # Compute averages over the repetitions
            avg_metrics = {
                "nodes": node_count,
                "rounds": 5,
                "total_runtime_sec": round(sum(m["total_runtime_sec"] for m in rep_metrics) / repetitions, 2),
                "avg_round_sec": round(sum(m["avg_round_sec"] for m in rep_metrics) / repetitions, 2),
                "aggregation_ms": round(sum(m["aggregation_ms"] for m in rep_metrics) / repetitions, 3),
                "heartbeat_ms": round(sum(m["heartbeat_ms"] for m in rep_metrics) / repetitions, 3),
                "heartbeats": round(sum(m["heartbeats"] for m in rep_metrics) / repetitions),
                "audit_entries": round(sum(m["audit_entries"] for m in rep_metrics) / repetitions),
                "metrics_records": round(sum(m["metrics_records"] for m in rep_metrics) / repetitions),
                "cpu_percent": round(sum(m["cpu_percent"] for m in rep_metrics) / repetitions, 2),
                "peak_memory_mb": round(max(m["peak_memory_mb"] for m in rep_metrics), 1)  # Peak RSS over all runs
            }
            results.append(avg_metrics)
            logger.info(f"Avg Result for {node_count} nodes: {avg_metrics}")
            
        except Exception as err:
            logger.error(f"Benchmark iteration for node scale {node_count} failed: {err}")
            cleanup_dbs()
            sys.exit(1)
            
    # Write to CSV
    os.makedirs("results", exist_ok=True)
    csv_file = "results/end_to_end_performance.csv"
    
    keys = ["nodes", "rounds", "total_runtime_sec", "avg_round_sec", "aggregation_ms", "heartbeat_ms", "heartbeats", "audit_entries", "metrics_records", "cpu_percent", "peak_memory_mb"]
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
