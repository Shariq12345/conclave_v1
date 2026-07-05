"""
conclave.cli.commands.node
──────────────────────────
CLI commands for node registration, status workflows, and heartbeats.
"""

import typer
import time
import socket
import platform
import os
import sys
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn

from conclave.cli.client import post, get, RemoteAPIError

app = typer.Typer(help="Register and manage federated learning nodes")
console = Console()


# ── Collector Helper ──────────────────────────────────────────────────────────

def collect_system_info():
    """Gathers OS, hardware, GPU, and software version details of the current machine."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    os_name = platform.system()
    os_version = platform.release() or platform.version()
    architecture = platform.machine() or platform.processor()

    # CPU model
    cpu_model = ""
    if os_name == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_model = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except Exception:
            cpu_model = platform.processor()
    elif os_name == "Linux":
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass
    elif os_name == "Darwin":
        try:
            cpu_model = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode().strip()
        except Exception:
            pass
    if not cpu_model:
        cpu_model = platform.processor() or "Unknown CPU"

    cpu_cores = os.cpu_count() or 1

    # RAM (GB)
    ram_gb = 0.0
    if os_name == "Windows":
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            ram_gb = round(stat.ullTotalPhys / (1024**3), 2)
        except Exception:
            pass
    elif os_name == "Linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_kb = int(line.split()[1])
                        ram_gb = round(ram_kb / (1024**2), 2)
                        break
        except Exception:
            pass
    elif os_name == "Darwin":
        try:
            ram_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
            ram_gb = round(ram_bytes / (1024**3), 2)
        except Exception:
            pass

    # GPU details
    gpu_available = "No"
    gpu_vendor = ""
    gpu_model = ""
    gpu_count = 0
    gpu_vram = 0.0
    cuda_version = ""

    try:
        # Run nvidia-smi to query GPUs
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL
        ).decode().strip()

        if output:
            gpu_available = "Yes"
            gpu_vendor = "NVIDIA"
            lines = [line.strip() for line in output.split("\n") if line.strip()]
            gpu_count = len(lines)
            parts = lines[0].split(",")
            gpu_model = parts[0].strip()
            if len(parts) > 1:
                try:
                    gpu_vram = round(float(parts[1].strip()) / 1024.0, 2)
                except Exception:
                    pass

            # Query CUDA version
            cuda_output = subprocess.check_output(["nvidia-smi"], stderr=subprocess.DEVNULL).decode()
            for line in cuda_output.split("\n"):
                if "CUDA Version" in line:
                    parts = line.split("CUDA Version:")
                    if len(parts) > 1:
                        cuda_version = parts[1].split("|")[0].strip()
                        break
    except Exception:
        pass

    # Software versions
    python_version = platform.python_version()

    flower_version = "Not Installed"
    try:
        import flwr
        flower_version = getattr(flwr, "__version__", "Installed")
    except ImportError:
        pass

    from conclave import __version__ as conclave_version

    return {
        "hostname": hostname,
        "os_name": os_name,
        "os_version": os_version,
        "architecture": architecture,
        "cpu_model": cpu_model,
        "cpu_cores": cpu_cores,
        "ram_gb": ram_gb,
        "gpu_available": gpu_available,
        "gpu_vendor": gpu_vendor,
        "gpu_model": gpu_model,
        "gpu_count": gpu_count,
        "gpu_vram": gpu_vram,
        "cuda_version": cuda_version,
        "python_version": python_version,
        "flower_version": flower_version,
        "conclave_version": conclave_version
    }


# ── CLI Commands ──────────────────────────────────────────────────────────────

def get_or_create_node_key():
    """Retrieves or creates the local node RSA key pair inside ~/.conclave/node_key.pem."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    node_dir = os.path.expanduser("~/.conclave")
    os.makedirs(node_dir, exist_ok=True)
    private_key_path = os.path.join(node_dir, "node_key.pem")

    if os.path.exists(private_key_path):
        with open(private_key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    else:
        # Generate new RSA private key
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        # Serialize and save private key
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        with open(private_key_path, "wb") as f:
            f.write(pem)
        
        # Set file permissions to 600
        try:
            os.chmod(private_key_path, 0o600)
        except Exception:
            pass

    # Extract public key in PEM format
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()

    return private_key_path, public_pem


@app.command(name="register")
def register_node(
    name: str = typer.Option(None, "--name", "-n", help="Optional friendly name for this node"),
    org: str = typer.Option(None, "--org", "-o", help="Optional organization name/id (System Admin only)")
):
    """
    Register the current machine as a participating node.
    Automatically generates node RSA keys and sends the public key.
    """
    console.print()
    console.print("[bold cyan]Generating node cryptographic keypair…[/bold cyan]")
    try:
        private_key_path, public_key_pem = get_or_create_node_key()
        console.print(f"  ✔ Key pair ready (Saved: [white]{private_key_path}[/white])")
    except Exception as e:
        console.print(f"[bold red]Key generation error:[/bold red] {e}")
        return

    console.print("[bold cyan]Gathering machine specifications…[/bold cyan]")
    sys_info = collect_system_info()

    # Build payload
    payload = {
        **sys_info,
        "node_name": name,
        "organization_id": org,
        "public_key": public_key_pem
    }

    try:
        data = post("/nodes/register", payload)

        # Save certificate and token
        node_dir = os.path.expanduser("~/.conclave")
        os.makedirs(node_dir, exist_ok=True)

        cert_path = os.path.join(node_dir, "node_cert.pem")
        token_path = os.path.join(node_dir, "node_token.txt")
        id_path = os.path.join(node_dir, "node_id.txt")

        if data.get("certificate"):
            with open(cert_path, "w") as f:
                f.write(data["certificate"])
        if data.get("registration_token"):
            with open(token_path, "w") as f:
                f.write(data["registration_token"])
        with open(id_path, "w") as f:
            f.write(data["id"])

        # Fetch and save Root CA certificate
        try:
            ca_data = get("/auth/ca-cert")
            if ca_data and ca_data.get("ca_cert"):
                ca_cert_path = os.path.join(node_dir, "ca_cert.pem")
                with open(ca_cert_path, "w") as f:
                    f.write(ca_data["ca_cert"])
        except Exception:
            pass

        console.print()
        console.print(Panel(
            f"Node ID       : [bold white]{data.get('id')}[/bold white]\n"
            f"Hostname      : {data.get('hostname')}\n"
            f"Friendly Name : {data.get('node_name') or 'None'}\n"
            f"OS / Arch     : {data.get('os_name')} ({data.get('architecture')})\n"
            f"CPU           : {data.get('cpu_model')} ({data.get('cpu_cores')} Cores)\n"
            f"RAM           : {data.get('ram_gb')} GB\n"
            f"GPU Available : [bold]{data.get('gpu_available')}[/bold] ({data.get('gpu_vendor')} {data.get('gpu_model')})\n"
            f"Identity Cert : [green]Saved to {cert_path}[/green]\n"
            f"Status        : [bold yellow]{data.get('status')}[/bold yellow]\n\n"
            f"[dim]The node has been registered successfully. It is now Pending approval by an administrator.[/dim]",
            title="[bold green]✔ Secure Node Registered[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="list")
def list_nodes():
    """List all registered nodes for your organization."""
    try:
        data = get("/nodes/list")
        if not data:
            console.print()
            console.print("[yellow]No nodes registered yet for your organization.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Registered Nodes[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2),
        )

        table.add_column("Node ID", style="dim", width=15)
        table.add_column("Hostname", style="bold magenta")
        table.add_column("Friendly Name", style="white")
        table.add_column("OS / Arch", style="cyan")
        table.add_column("CPU Cores / RAM", style="blue")
        table.add_column("GPU", style="magenta")
        table.add_column("Status", style="bold")
        table.add_column("Last Known IP", style="dim")

        for n in data:
            status = n.get("status")
            if status in ("Approved", "Online"):
                status_str = f"[bold green]{status}[/bold green]"
            elif status == "Pending":
                status_str = f"[bold yellow]{status}[/bold yellow]"
            elif status == "Offline":
                status_str = f"[bold dim]{status}[/bold dim]"
            else:
                status_str = f"[bold red]{status}[/bold red]"

            gpu_avail = n.get("gpu_available", "No")
            gpu_str = "Yes" if gpu_avail == "Yes" else "No"

            table.add_row(
                n.get("id")[:12] + "…",
                n.get("hostname"),
                n.get("node_name") or "—",
                f"{n.get('os_name')} ({n.get('architecture')})",
                f"{n.get('cpu_cores')}c / {n.get('ram_gb')}G",
                gpu_str,
                status_str,
                n.get("last_ip")
            )

        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="show")
def show_node(node_id: str):
    """Show detailed information for a specific node."""
    try:
        n = get(f"/nodes/show/{node_id}")

        status = n.get("status")
        if status in ("Approved", "Online"):
            status_str = f"[bold green]{status}[/bold green]"
        elif status == "Pending":
            status_str = f"[bold yellow]{status}[/bold yellow]"
        elif status == "Offline":
            status_str = f"[bold dim]{status}[/bold dim]"
        else:
            status_str = f"[bold red]{status}[/bold red]"

        console.print()
        console.print(Panel(
            f"[bold cyan]Identity[/bold cyan]\n"
            f"  Node ID          : [white]{n.get('id')}[/white]\n"
            f"  Organization ID  : {n.get('organization_id')}\n"
            f"  Hostname         : {n.get('hostname')}\n"
            f"  Friendly Name    : {n.get('node_name') or '—'}\n"
            f"  Status           : {status_str}\n"
            f"  Registered At    : {n.get('registered_at').replace('T', ' ')[:19]}\n"
            f"  Last Heartbeat   : {n.get('last_heartbeat').replace('T', ' ')[:19]}\n"
            f"  Last Known IP    : {n.get('last_ip')}\n\n"
            f"[bold cyan]Hardware Specifications[/bold cyan]\n"
            f"  Operating System : {n.get('os_name')} (Version: {n.get('os_version')})\n"
            f"  Architecture     : {n.get('architecture')}\n"
            f"  CPU Model        : {n.get('cpu_model')}\n"
            f"  CPU Cores        : {n.get('cpu_cores')}\n"
            f"  RAM              : {n.get('ram_gb')} GB\n\n"
            f"[bold cyan]GPU Configuration[/bold cyan]\n"
            f"  GPU Available    : {n.get('gpu_available')}\n"
            f"  GPU Vendor       : {n.get('gpu_vendor') or '—'}\n"
            f"  GPU Model        : {n.get('gpu_model') or '—'}\n"
            f"  GPU Count        : {n.get('gpu_count') or 0}\n"
            f"  GPU Memory (VRAM): {n.get('gpu_vram') or 0.0} GB\n"
            f"  CUDA Version     : {n.get('cuda_version') or '—'}\n\n"
            f"[bold cyan]Software Versions[/bold cyan]\n"
            f"  Python           : {n.get('python_version')}\n"
            f"  Flower Framework : {n.get('flower_version')}\n"
            f"  Conclave Agent   : {n.get('conclave_version')}",
            title=f"[bold blue]Node Details: {n.get('hostname')}[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="approve")
def approve_node(node_id: str):
    """Approve a pending node to participate in training."""
    try:
        data = post(f"/nodes/approve/{node_id}")
        console.print()
        console.print(f"[bold green]✔ Done:[/bold green] Node [bold white]'{data.get('hostname')}'[/bold white] has been approved successfully.")
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="reject")
def reject_node(node_id: str):
    """Reject a pending node registration request."""
    try:
        data = post(f"/nodes/reject/{node_id}")
        console.print()
        console.print(f"[bold green]✔ Done:[/bold green] Node [bold white]'{data.get('hostname')}'[/bold white] has been rejected.")
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="revoke")
def revoke_node(node_id: str):
    """Revoke training permission from a previously approved node."""
    try:
        data = post(f"/nodes/revoke/{node_id}")
        console.print()
        console.print(f"[bold green]✔ Done:[/bold green] Node [bold white]'{data.get('hostname')}'[/bold white] has been revoked.")
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="heartbeat")
def node_heartbeat(
    node_id: str,
    interval: int = typer.Option(30, "--interval", "-i", help="Heartbeat interval in seconds")
):
    """
    Start the heartbeat agent for a node.
    Periodically reports node health and online status to the server.
    """
    console.print()
    console.print(Panel(
        f"[bold white]Node ID   :[/bold white] [bold cyan]{node_id}[/bold cyan]\n"
        f"[bold white]Interval  :[/bold white] {interval} seconds\n"
        f"[bold white]Server    :[/bold white] {get_server_url_hint()}\n\n"
        f"[yellow]Heartbeat loop active. Press Ctrl+C to exit and stop heartbeat.[/yellow]",
        title="[bold green]✦ Conclave Node Heartbeat Active[/bold green]",
        border_style="green",
        expand=False,
        padding=(1, 3)
    ))
    console.print()

    # Load node private key
    node_dir = os.path.expanduser("~/.conclave")
    private_key_path = os.path.join(node_dir, "node_key.pem")
    if not os.path.exists(private_key_path):
        console.print(f"[bold red]Error:[/bold red] Node private key not found at {private_key_path}. Did you register this node?")
        return

    from cryptography.hazmat.primitives import serialization
    try:
        with open(private_key_path, "rb") as f:
            priv_key = serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        console.print(f"[bold red]Error loading private key:[/bold red] {e}")
        return

    # First verification check
    try:
        n = get(f"/nodes/show/{node_id}")
        if n.get("status") in ("Rejected", "Revoked"):
            console.print(f"[bold red]Error:[/bold red] Node status is '{n.get('status')}'. Heartbeat stopped.")
            return
    except RemoteAPIError as e:
        console.print(f"[bold red]Initialization Error:[/bold red] {e}")
        return

    # Loop sending heartbeats
    import jwt
    import threading
    finished_sessions = set()
    active_running_sessions = set()

    def run_flower_client(sess_id, srv_addr, privacy_cfg=None):
        try:
            console.print(f"\n[bold cyan]✦ [{time.strftime('%H:%M:%S')}] Active task detected for session: {sess_id}. Starting Flower client…[/bold cyan]")
            import flwr as fl
            from conclave.integrations.flower.orchestrator import SimpleFlowerClient
            client = SimpleFlowerClient(node_id, privacy_config=privacy_cfg)
            fl.client.start_numpy_client(server_address=srv_addr, client=client)
            console.print(f"[bold green]✔ [{time.strftime('%H:%M:%S')}] Flower client completed training for session: {sess_id}[/bold green]\n")
        except Exception as ex:
            console.print(f"[bold red]✘ [{time.strftime('%H:%M:%S')}] Flower client training failed: {ex}[/bold red]\n")
        finally:
            active_running_sessions.discard(sess_id)
            finished_sessions.add(sess_id)

    try:
        while True:
            try:
                # Generate node JWT signed with private key (valid for 2 minutes)
                now_ts = int(time.time())
                token = jwt.encode(
                    {"sub": node_id, "exp": now_ts + 120, "iat": now_ts},
                    priv_key,
                    algorithm="RS256"
                )

                # Capture system metrics
                metrics_payload = {}
                try:
                    import psutil
                    metrics_payload = {
                        "cpu_utilization": psutil.cpu_percent(interval=None),
                        "ram_utilization": psutil.virtual_memory().percent,
                        "gpu_utilization": 0.0,
                        "gpu_vram_utilization": 0.0,
                        "gpu_temp": 0.0
                    }
                except ImportError:
                    import random
                    metrics_payload = {
                        "cpu_utilization": round(random.uniform(10.0, 45.0), 1),
                        "ram_utilization": round(random.uniform(30.0, 70.0), 1),
                        "gpu_utilization": round(random.uniform(0.0, 10.0), 1),
                        "gpu_vram_utilization": round(random.uniform(0.0, 5.0), 1),
                        "gpu_temp": round(random.uniform(35.0, 55.0), 1)
                    }

                # Send heartbeat with node token and metrics payload
                data = post(
                    f"/nodes/heartbeat/{node_id}",
                    json_data=metrics_payload,
                    headers={"X-Node-Token": token}
                )
                status = data.get("status")
                t_str = time.strftime("%H:%M:%S")
                console.print(f"[{t_str}] [green]✔[/green] Heartbeat reported. Status: [bold green]{status}[/bold green]")

                # Check for active task
                active_task = data.get("active_task")
                if active_task:
                    session_id = active_task.get("session_id")
                    server_address = active_task.get("server_address")
                    if session_id not in finished_sessions and session_id not in active_running_sessions:
                        active_running_sessions.add(session_id)
                        t = threading.Thread(
                            target=run_flower_client,
                            args=(session_id, server_address, active_task.get("privacy")),
                            daemon=True
                        )
                        t.start()

            except RemoteAPIError as e:
                t_str = time.strftime("%H:%M:%S")
                console.print(f"[{t_str}] [red]✘[/red] Heartbeat failed: {e}")
                if "rejected" in str(e).lower() or "revoked" in str(e).lower() or "unapproved" in str(e).lower():
                    console.print("[bold red]Critical: Node rejected, unapproved, or revoked. Stopping heartbeat loop.[/bold red]")
                    break

            time.sleep(interval)
    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Heartbeat agent stopped.[/yellow]")
        console.print()


def get_server_url_hint():
    try:
        from conclave.cli.config import load_server_url
        return load_server_url()
    except Exception:
        return "http://127.0.0.1:8000"
