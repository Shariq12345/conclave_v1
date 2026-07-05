#!/usr/bin/env python3
"""
conclave.benchmarks.benchmark_node_scalability
────────────────────────────────────────────────
Scalability benchmark to measure how Conclave performs as the number
of simulated hospital nodes increases.

Evaluates the orchestration layer, heartbeat scheduler, and federated learning coordinator.
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
logger = logging.getLogger("conclave_bench")

# Configuration Constants
DB_FILE = "conclave_scalability_bench.db"
METRICS_DB_FILE = "conclave_bench_metrics.db"
FLOWER_PORT = 8080


def set_reproducible_seed(seed: int):
    """Sets standard seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    logger.info(f"Reproducible random seed set to: {seed}")


def is_port_free(port: int) -> bool:
    """Checks if a local TCP port is free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except socket.error:
            return False


def wait_for_port_free(port: int, timeout: int = 15):
    """Waits until a local port is free."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_port_free(port):
            return True
        time.sleep(0.5)
    return False


def init_wal_dbs():
    """Initializes sqlite databases and sets WAL journal mode to improve concurrency."""
    for db in [DB_FILE, METRICS_DB_FILE]:
        if os.path.exists(db):
            try:
                os.remove(db)
            except Exception as e:
                logger.warning(f"Failed to remove stale db {db}: {e}")
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.commit()
            conn.close()
            logger.info(f"Initialized database {db} in WAL mode.")
        except Exception as e:
            logger.error(f"Error initializing WAL db {db}: {e}")


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
    """Periodically monitors combined CPU and peak RAM utilization of the parent and child processes."""
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
        self.end_time = time.time()

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
        """Registers the node specs and public key, then approves the registration."""
        register_payload = {
            "organization_id": org_id,
            "hostname": self.hostname,
            "node_name": f"Simulated Hospital Node {self.node_index}",
            "os_name": "Linux" if sys.platform != "win32" else "Windows",
            "os_version": "Bench-1.0",
            "architecture": "x86_64",
            "cpu_model": "Simulated Bench CPU",
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
            # Sign token
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
                latency_ms = (time.time() - t0) * 1000
                if r.status_code == 200:
                    self.heartbeat_latencies.append(latency_ms)
                    self.heartbeat_count += 1
                    resp_data = r.json()
                    
                    # Check for active training task
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
        """Starts a background Flower client thread connecting to the server's training port."""
        self.flower_thread = threading.Thread(
            target=self._run_flower_client,
            args=(active_task,),
            daemon=True
        )
        self.flower_thread.start()

    def _run_flower_client(self, active_task: dict):
        """Standard NumPy client training execution."""
        server_address = active_task["server_address"]
        privacy_cfg = active_task.get("privacy", {})
        
        try:
            import flwr as fl
            from conclave.integrations.flower.orchestrator import SimpleFlowerClient
            
            # SimpleFlowerClient simulates local training via sleep(0.2s) in fit()
            client = SimpleFlowerClient(self.hostname, privacy_config=privacy_cfg)
            fl.client.start_numpy_client(server_address=server_address, client=client)
            self.training_completed = True
            logger.info(f"Node {self.hostname} successfully completed training task.")
        except Exception as e:
            logger.error(f"Flower client error on node {self.hostname}: {e}")
        finally:
            # Once training is done, we can stop heartbeating
            self.stop_heartbeat.set()


def run_single_benchmark_iteration(node_count: int, seed: int) -> dict:
    """Runs the complete registration, heartbeat, and training cycle for N nodes."""
    logger.info(f"\n==========================================")
    logger.info(f"Starting Scale Test: {node_count} Node(s)")
    logger.info(f"==========================================")
    
    set_reproducible_seed(seed)
    init_wal_dbs()
    
    server_port = 8000 + node_count
    server_url = f"http://127.0.0.1:{server_port}"
    
    # 1. Start Server
    server_env = os.environ.copy()
    server_env["CONCLAVE_DB_FILE"] = DB_FILE
    server_env["CONCLAVE_METRICS_DB_FILE"] = METRICS_DB_FILE
    server_env["BYPASS_AUTH"] = "true"
    server_env["TESTING"] = "true"
    
    cmd = [
        sys.executable,
        "-c",
        f"import uvicorn; from conclave.server.main import app; uvicorn.run(app, host='127.0.0.1', port={server_port}, log_level='error')"
    ]
    
    server_proc = subprocess.Popen(cmd, env=server_env)
    
    # Measure execution start
    iter_start_time = time.time()
    resource_monitor: Optional[ResourceMonitor] = None
    nodes: List[SimulatedNode] = []
    training_duration = 0.0
    
    try:
        # Wait for FastAPI server to respond
        logger.info(f"Waiting for Conclave Server to bind on port {server_port}...")
        server_ready = False
        for _ in range(30):
            try:
                r = requests.get(f"{server_url}/nodes/list", timeout=1)
                if r.status_code == 200:
                    server_ready = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
            
        if not server_ready:
            raise RuntimeError(f"FastAPI Server failed to start on port {server_port}")
            
        logger.info("Conclave server is ready. Setting up metadata...")
        
        # 2. Pre-seed Organization
        r_org = requests.post(
            f"{server_url}/organizations/create",
            json={"name": "test_org", "organization_type": "Hospital", "description": "Benchmark Org"}
        )
        if r_org.status_code != 200:
            raise RuntimeError(f"Failed to create organization: {r_org.text}")
        org_id = r_org.json()["id"]
        
        # 3. Register Governance Client (to satisfy consent verification rule)
        r_client = requests.post(
            f"{server_url}/clients/register",
            json={"name": "test_org"}
        )
        if r_client.status_code != 200:
            raise RuntimeError(f"Failed to register governance client: {r_client.text}")

        # 4. Grant Consent (to satisfy consent verification rule on dataset 'test_dataset')
        r_consent = requests.post(
            f"{server_url}/consents/grant",
            json={"client_name": "test_org", "dataset_name": "test_dataset"}
        )
        if r_consent.status_code != 200:
            raise RuntimeError(f"Failed to grant client consent: {r_consent.text}")
        
        # 5. Pre-seed Policy
        r_pol = requests.post(
            f"{server_url}/policies/create",
            json={"name": "default_policy", "description": "Benchmark Policy", "secagg_enabled": False, "dp_enabled": False}
        )
        if r_pol.status_code != 200:
            raise RuntimeError(f"Failed to create policy: {r_pol.text}")
            
        # 6. Generate keys & register nodes under org_id
        logger.info(f"Generating RSA key pairs and registering {node_count} nodes...")
        for i in range(1, node_count + 1):
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pub_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode()
            
            node = SimulatedNode(
                node_index=i,
                hostname=f"node_{node_count}_{i}",
                server_url=server_url,
                private_key=private_key,
                public_key_pem=pub_pem
            )
            if not node.register_and_approve(org_id):
                raise RuntimeError(f"Could not register/approve simulated node {i}")
            nodes.append(node)
            
        # 7. Start monitoring resources
        resource_monitor = ResourceMonitor(os.getpid(), interval=0.1)
        resource_monitor.start()
        
        # 8. Start Heartbeat loops
        logger.info("Activating heartbeat loop for nodes...")
        for node in nodes:
            node.start_heartbeat_loop()
            
        # 9. Wait until all nodes are "Online"
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
            
        logger.info("All nodes are Online. Creating and launching training session...")
        
        # 10. Create training session
        r_session = requests.post(
            f"{server_url}/trainings/create",
            json={
                "name": f"session_{node_count}",
                "participating_clients": ["test_org"],
                "assigned_policy": "default_policy",
                "dataset_name": "test_dataset",
                "description": "Hospital scale test",
                "priority": "Medium"
            }
        )
        if r_session.status_code != 200:
            raise RuntimeError(f"Failed to create training session: {r_session.text}")
            
        # 11. Start training session (blocks until completed)
        training_start = time.time()
        r_start = requests.post(f"{server_url}/trainings/start/session_{node_count}", timeout=120)
        training_duration = time.time() - training_start
        
        if r_start.status_code != 200:
            raise RuntimeError(f"Training session run failed: {r_start.text}")
            
        logger.info(f"Training session complete! Duration: {training_duration:.2f} seconds.")
        
        # Wait for heartbeat loops to wrap up/finish cleanly
        time.sleep(1.0)
        
    except Exception as e:
        logger.error(f"Benchmark iteration failed with error: {e}")
        # Make sure we stop heartbeat threads
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
            
        # Clean up database files
        cleanup_dbs()
        
    # Aggregate latencies and heartbeats
    all_latencies = []
    total_hb = 0
    for node in nodes:
        all_latencies.extend(node.heartbeat_latencies)
        total_hb += node.heartbeat_count
        
    avg_hb_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
    avg_round_time = training_duration / 3.0  # 3 rounds
    
    return {
        "nodes": node_count,
        "total_runtime_sec": round(iter_runtime, 2),
        "avg_heartbeat_ms": round(avg_hb_latency, 2),
        "avg_round_time_sec": round(avg_round_time, 2),
        "total_heartbeats": total_hb,
        "cpu_percent": round(avg_cpu, 1),
        "peak_memory_mb": round(peak_mem, 1)
    }


def generate_figures(results: List[dict]):
    """Generates publication-quality runtime and latency figures using Matplotlib."""
    logger.info("Generating publication-quality graphs...")
    
    import matplotlib.pyplot as plt
    
    nodes = [r["nodes"] for r in results]
    runtimes = [r["total_runtime_sec"] for r in results]
    latencies = [r["avg_heartbeat_ms"] for r in results]
    
    os.makedirs("figures", exist_ok=True)
    
    # Style configuration
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

    # --- Figure 1: Runtime Scale ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(nodes, runtimes, marker="o", markersize=6, color="#4F46E5", linewidth=2.0, label="Total Runtime")
    ax.set_title("Orchestration Runtime Scalability", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Number of Simulated Nodes", fontsize=10, labelpad=8)
    ax.set_ylabel("Execution Time (seconds)", fontsize=10, labelpad=8)
    ax.set_xticks(nodes)
    ax.grid(True, linestyle="--", alpha=0.7)
    
    # Minimalist aesthetics
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#9CA3AF")
    ax.spines["bottom"].set_color("#9CA3AF")
    
    # Save Figure 1
    plt.tight_layout()
    plt.savefig("figures/node_runtime.png", dpi=300)
    plt.savefig("figures/node_runtime.svg", format="svg")
    plt.savefig("figures/node_runtime.pdf", format="pdf")
    plt.close()
    
    # --- Figure 2: Heartbeat Latency Scale ---
    fig, ax = plt.subplots(figsize=(6, 4.5), dpi=300)
    ax.plot(nodes, latencies, marker="s", markersize=6, color="#06B6D4", linewidth=2.0, label="Heartbeat Latency")
    ax.set_title("Heartbeat Latency Scalability", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Number of Simulated Nodes", fontsize=10, labelpad=8)
    ax.set_ylabel("Average Latency (ms)", fontsize=10, labelpad=8)
    ax.set_xticks(nodes)
    ax.grid(True, linestyle="--", alpha=0.7)
    
    # Minimalist aesthetics
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#9CA3AF")
    ax.spines["bottom"].set_color("#9CA3AF")
    
    # Save Figure 2
    plt.tight_layout()
    plt.savefig("figures/heartbeat_latency.png", dpi=300)
    plt.savefig("figures/heartbeat_latency.svg", format="svg")
    plt.savefig("figures/heartbeat_latency.pdf", format="pdf")
    plt.close()
    
    logger.info("Figures successfully generated in PNG (300 DPI), SVG, and PDF formats.")


def main():
    parser = argparse.ArgumentParser(description="Conclave Hospital Node Scalability Benchmark")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()
    
    logger.info("Starting Conclave Node Scalability Benchmark...")
    
    target_nodes = [1, 3, 5, 10, 20]
    results = []
    
    # Process bar across different node configurations
    for node_count in tqdm(target_nodes, desc="Benchmarking Node Scale", unit="config"):
        try:
            metrics = run_single_benchmark_iteration(node_count, args.seed)
            results.append(metrics)
            logger.info(f"Result for {node_count} nodes: {metrics}")
            
            # Brief cooldown period between configs
            time.sleep(2.0)
        except Exception as err:
            logger.error(f"Benchmark iteration for node scale {node_count} failed: {err}")
            cleanup_dbs()
            sys.exit(1)
            
    # Write to CSV
    os.makedirs("results", exist_ok=True)
    csv_file = "results/node_scalability.csv"
    
    keys = ["nodes", "total_runtime_sec", "avg_heartbeat_ms", "avg_round_time_sec", "total_heartbeats", "cpu_percent", "peak_memory_mb"]
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
