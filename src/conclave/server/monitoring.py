import os
import uuid
import time
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

METRICS_DB_FILE = os.getenv("CONCLAVE_METRICS_DB_FILE", "conclave_metrics.db")

class MetricsDB:
    """
    Independent SQLite storage for real-time node and session metrics.
    """
    def __init__(self, db_path: str = METRICS_DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        # Disable same thread check since background monitoring service runs in a separate thread
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS node_metrics (
                    node_id TEXT,
                    timestamp DATETIME,
                    cpu REAL,
                    ram REAL,
                    gpu REAL,
                    gpu_vram REAL,
                    gpu_temp REAL,
                    status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_metrics (
                    session_id TEXT,
                    timestamp DATETIME,
                    current_round INTEGER,
                    total_rounds INTEGER,
                    status TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    timestamp DATETIME,
                    severity TEXT,
                    source TEXT,
                    source_id TEXT,
                    message TEXT,
                    resolved INTEGER DEFAULT 0
                )
            """)
            conn.commit()


class MonitoringService:
    """
    Real-Time Monitoring Service. Tracks metrics, processes alerts, and triggers background checks.
    """
    def __init__(self, registry=None):
        self.db = MetricsDB()
        self.registry = registry  # ServiceRegistry reference (resolved at runtime to prevent circular import)
        self._stop_event = threading.Event()
        self._monitor_thread = None

    def log_node_metrics(self, node_id: str, cpu: float, ram: float, gpu: float, gpu_vram: float, gpu_temp: float, status: str = "Online"):
        with self.db._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO node_metrics (node_id, timestamp, cpu, ram, gpu, gpu_vram, gpu_temp, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (node_id, datetime.now().isoformat(), cpu, ram, gpu, gpu_vram, gpu_temp, status)
            )
            conn.commit()

    def log_session_metrics(self, session_id: str, current_round: int, total_rounds: int, status: str):
        with self.db._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO session_metrics (session_id, timestamp, current_round, total_rounds, status) VALUES (?, ?, ?, ?, ?)",
                (session_id, datetime.now().isoformat(), current_round, total_rounds, status)
            )
            conn.commit()

    def create_alert(self, severity: str, source: str, source_id: str, message: str) -> dict:
        alert_id = str(uuid.uuid4())
        with self.db._get_conn() as conn:
            cursor = conn.cursor()
            # Prevent duplicate unresolved alerts for the same source/id
            cursor.execute("SELECT id FROM alerts WHERE source = ? AND source_id = ? AND resolved = 0", (source, source_id))
            if cursor.fetchone():
                return {} # Alert already active
            
            cursor.execute(
                "INSERT INTO alerts (id, timestamp, severity, source, source_id, message, resolved) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (alert_id, datetime.now().isoformat(), severity, source, source_id, message)
            )
            conn.commit()
        return {"id": alert_id, "severity": severity, "message": message}

    def resolve_alert(self, alert_id: str) -> bool:
        with self.db._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_latest_node_metrics(self, node_id: str) -> Optional[dict]:
        with self.db._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT cpu, ram, gpu, gpu_vram, gpu_temp, status, timestamp FROM node_metrics WHERE node_id = ? ORDER BY timestamp DESC LIMIT 1",
                (node_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "cpu": row[0],
                    "ram": row[1],
                    "gpu": row[2],
                    "gpu_vram": row[3],
                    "gpu_temp": row[4],
                    "status": row[5],
                    "timestamp": row[6]
                }
            return None

    def get_latest_session_metrics(self, session_id: str) -> Optional[dict]:
        with self.db._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_round, total_rounds, status, timestamp FROM session_metrics WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "current_round": row[0],
                    "total_rounds": row[1],
                    "status": row[2],
                    "timestamp": row[3]
                }
            return None

    def get_active_alerts(self) -> List[dict]:
        with self.db._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, timestamp, severity, source, source_id, message FROM alerts WHERE resolved = 0 ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            return [{
                "id": r[0],
                "timestamp": r[1],
                "severity": r[2],
                "source": r[3],
                "source_id": r[4],
                "message": r[5]
            } for r in rows]

    def get_status_summary(self) -> dict:
        if not self.registry:
            from conclave.server.registry import ServiceRegistry
            self.registry = ServiceRegistry()

        # Gather node details and statuses
        nodes = self.registry.node_service.list_nodes()
        nodes_summary = []
        for n in nodes:
            metrics = self.get_latest_node_metrics(n.id) or {
                "cpu": 0.0, "ram": 0.0, "gpu": 0.0, "gpu_vram": 0.0, "gpu_temp": 0.0, "status": n.status
            }
            # Adjust status based on busy training states
            status_display = n.status
            if n.status == "Online":
                task = self.registry.training_service.orchestrator.get_active_task(n.id)
                if task:
                    status_display = "Busy"
                else:
                    status_display = "Idle"

            nodes_summary.append({
                "id": n.id,
                "hostname": n.hostname,
                "org_id": n.organization_id,
                "status": status_display,
                "last_heartbeat": n.last_heartbeat.isoformat() if n.last_heartbeat else None,
                "metrics": metrics
            })

        # Gather session metrics
        sessions = self.registry.training_service.repository.find_all()
        sessions_summary = []
        for s in sessions:
            if s.status in ("Running", "Preempted", "Failed", "Interrupted"):
                metrics = self.get_latest_session_metrics(s.id) or {
                    "current_round": 0, "total_rounds": 3, "status": s.status
                }
                sessions_summary.append({
                    "id": s.id,
                    "name": s.name,
                    "status": s.status,
                    "priority": s.priority,
                    "dataset": s.dataset_name,
                    "current_round": metrics["current_round"],
                    "total_rounds": metrics["total_rounds"]
                })

        return {
            "nodes": nodes_summary,
            "sessions": sessions_summary,
            "alerts": self.get_active_alerts(),
            "timestamp": datetime.now().isoformat()
        }

    def start_background_monitor(self):
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_background_monitor(self):
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)

    def check_node_health(self):
        try:
            if not self.registry:
                from conclave.server.registry import ServiceRegistry
                self.registry = ServiceRegistry()

            nodes = self.registry.node_service.list_nodes()
            for n in nodes:
                if n.status in ("Online", "Approved", "Busy", "Idle") and n.last_heartbeat:
                    delta = (datetime.now() - n.last_heartbeat).total_seconds()
                    # If no heartbeat for > 15 seconds, transition to Offline
                    if delta > 15.0:
                        print(f"BACKGROUND MONITOR: Missed heartbeat detected on {n.hostname} (delta: {delta:.2f}s). Transitioning to Offline.")
                        node_to_update = self.registry.node_service.get_node(n.id)
                        node_to_update.status = "Offline"
                        self.registry.node_service.node_repository.save(node_to_update)
                        
                        # Log alert in metrics DB
                        self.create_alert(
                            severity="Critical",
                            source="Node",
                            source_id=n.id,
                            message=f"Missed heartbeat: Node '{n.hostname}' went offline (last heartbeat: {delta:.1f} seconds ago)."
                        )
                        
                        # Log in audit chain
                        self.registry.audit_service.log_event(
                            event_type="NODE_OFFLINE",
                            resource_type="Node",
                            resource_name=n.hostname,
                            action="heartbeat_monitor",
                            status="Failure",
                            message=f"Node '{n.hostname}' went offline due to missed heartbeats."
                        )

                        # If active task in running session, fail the session
                        active_task = self.registry.training_service.orchestrator.get_active_task(n.id)
                        if active_task:
                            session_id = active_task.get("session_id")
                            if session_id:
                                try:
                                    session = self.registry.training_service.repository.find_by_id(session_id)
                                    if session and session.status == "Running":
                                        session.status = "Interrupted"
                                        self.registry.training_service.repository.save(session)
                                        
                                        self.create_alert(
                                            severity="Critical",
                                            source="Session",
                                            source_id=session_id,
                                            message=f"Training session '{session.name}' interrupted because active node '{n.hostname}' went offline."
                                        )
                                        
                                        self.registry.audit_service.log_event(
                                            event_type="TRAINING_INTERRUPTED",
                                            resource_type="TrainingSession",
                                            resource_name=session.name,
                                            action="execute",
                                            status="Failure",
                                            message=f"Training session interrupted due to offline active node '{n.hostname}'."
                                        )
                                except Exception:
                                    pass
        except Exception as err:
            import traceback
            print(f"BACKGROUND MONITOR CHECK ERROR: {err}")
            traceback.print_exc()

    def _monitor_loop(self):
        print("BACKGROUND MONITOR: thread loop started.")
        while not self._stop_event.is_set():
            self.check_node_health()
            # Check every 5 seconds
            time.sleep(5)
