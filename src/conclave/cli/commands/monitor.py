import typer
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, RemoteAPIError

app = typer.Typer(help="Monitor the health of nodes, training sessions, and system alerts")
console = Console()

@app.callback()
def callback():
    """
    Monitor command group callback.
    """
    pass


def draw_progress_bar(current: int, total: int, width: int = 15) -> str:
    if total <= 0:
        return "[dim]Pending[/dim]"
    pct = min(1.0, max(0.0, float(current) / float(total)))
    filled = int(round(pct * width))
    bar = "#" * filled + "-" * (width - filled)
    color = "green" if pct == 1.0 else "yellow" if pct > 0.0 else "red"
    return f"[{color}]{bar}[/{color}] [bold]{int(pct * 100)}%[/bold] ({current}/{total})"


from rich.console import Group
from rich.text import Text
from rich.live import Live

def render_monitor_dashboard() -> Panel:
    try:
        data = get("/monitor/status")
        renderables = []
        
        # 1. Header
        header = Text.from_markup(f"[bold cyan]*** Conclave Node & Governance Monitoring System ***[/bold cyan] [dim](Refreshed: {data.get('timestamp')})[/dim]")
        renderables.append(header)
        renderables.append(Text("")) # Spacer
        
        # 2. Nodes Health Table
        nodes_table = Table(
            title="[bold white]Node Utilization & Health Status[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 1)
        )
        nodes_table.add_column("Node ID", style="dim magenta")
        nodes_table.add_column("Hostname", style="bold white")
        nodes_table.add_column("Status", style="bold")
        nodes_table.add_column("CPU", justify="right")
        nodes_table.add_column("RAM", justify="right")
        nodes_table.add_column("GPU", justify="right")
        nodes_table.add_column("VRAM", justify="right")
        nodes_table.add_column("GPU Temp", justify="right")
        nodes_table.add_column("Last Heartbeat", style="cyan")

        for n in data.get("nodes", []):
            status = n["status"]
            metrics = n["metrics"]
            
            # Status colors
            if status == "Busy":
                status_str = "[bold orange3]Busy[/bold orange3]"
            elif status == "Idle" or status == "Online":
                status_str = "[bold green]Online[/bold green]"
            else:
                status_str = "[bold red]Offline[/bold red]"

            # Metrics colors based on utilization threshold
            cpu_val = metrics.get("cpu", 0.0)
            cpu_str = f"{cpu_val:.1f}%"
            if cpu_val > 80.0:
                cpu_str = f"[bold red]{cpu_str}[/bold red]"
            elif cpu_val > 50.0:
                cpu_str = f"[bold yellow]{cpu_str}[/bold yellow]"
            else:
                cpu_str = f"[green]{cpu_str}[/green]"

            ram_val = metrics.get("ram", 0.0)
            ram_str = f"{ram_val:.1f}%"
            if ram_val > 80.0:
                ram_str = f"[bold red]{ram_str}[/bold red]"
            elif ram_val > 50.0:
                ram_str = f"[bold yellow]{ram_str}[/bold yellow]"
            else:
                ram_str = f"[green]{ram_str}[/green]"

            gpu_val = metrics.get("gpu", 0.0)
            gpu_str = f"{gpu_val:.1f}%" if gpu_val > 0.0 else "[dim]N/A[/dim]"
            
            vram_val = metrics.get("gpu_vram", 0.0)
            vram_str = f"{vram_val:.1f}%" if vram_val > 0.0 else "[dim]N/A[/dim]"

            temp_val = metrics.get("gpu_temp", 0.0)
            temp_str = f"{temp_val:.1f}°C" if temp_val > 0.0 else "[dim]N/A[/dim]"

            # Heartbeat time formatter
            lh_str = "[red]Never[/red]"
            if n.get("last_heartbeat"):
                lh = n["last_heartbeat"].split(".")[0].replace("T", " ")
                lh_str = lh.split()[-1] # Only show time segment for compactness

            nodes_table.add_row(
                n["id"][:8],
                n["hostname"],
                status_str,
                cpu_str,
                ram_str,
                gpu_str,
                vram_str,
                temp_str,
                lh_str
            )
        renderables.append(nodes_table)
        renderables.append(Text("")) # Spacer

        # 3. Active Sessions Table
        sessions = data.get("sessions", [])
        if sessions:
            sess_table = Table(
                title="[bold white]Active Federated Learning Sessions[/bold white]",
                title_justify="left",
                box=box.ROUNDED,
                border_style="orange3",
                header_style="bold orange3",
                padding=(0, 2)
            )
            sess_table.add_column("Session ID", style="dim magenta")
            sess_table.add_column("Session Name", style="bold white")
            sess_table.add_column("Status", style="bold")
            sess_table.add_column("Priority", style="yellow")
            sess_table.add_column("Dataset", style="cyan")
            sess_table.add_column("Flower Training Round Progress", style="white")

            for s in sessions:
                status_style = "bold green" if s["status"] == "Completed" else "bold orange3" if s["status"] == "Running" else "bold red"
                sess_table.add_row(
                    s["id"][:8],
                    s["name"],
                    f"[{status_style}]{s['status']}[/{status_style}]",
                    s["priority"],
                    s["dataset"],
                    draw_progress_bar(s["current_round"], s["total_rounds"])
                )
            renderables.append(sess_table)
            renderables.append(Text("")) # Spacer

        # 4. Alerts Panel
        alerts = data.get("alerts", [])
        if alerts:
            alert_items = []
            for a in alerts:
                severity_color = "red" if a["severity"] == "Critical" else "yellow"
                alert_items.append(
                    f"• [[bold {severity_color}]{a['severity']}[/bold {severity_color}]] {a['message']} "
                    f"[dim](ID: {a['id'][:8]} | Source: {a['source']} {a['source_id'][:8]})[/dim]"
                )
            renderables.append(Panel(
                "\n".join(alert_items),
                title="[bold red][X] Active System Alerts[/bold red]",
                border_style="red",
                expand=True,
                padding=(1, 3)
            ))
        else:
            renderables.append(Panel(
                "[bold green][OK] All systems healthy. No active alerts.[/bold green]",
                border_style="green",
                expand=True,
                padding=(1, 3)
            ))
        
        return Panel(Group(*renderables), border_style="cyan", padding=(1, 2))
    except RemoteAPIError as e:
        return Panel(Text(f"Error querying status: {e}", style="bold red"), border_style="red", padding=(1, 2))

def display_monitor_dashboard():
    console.print(render_monitor_dashboard())

@app.command(name="status")
def monitor_status(
    watch: bool = typer.Option(False, "--watch", "-w", help="Periodically refresh status dashboard.")
):
    """
    Display Conclave real-time node metrics, active FL rounds progress, and active alerts.
    """
    if watch:
        try:
            with Live(render_monitor_dashboard(), console=console, refresh_per_second=0.5) as live:
                while True:
                    time.sleep(2)
                    live.update(render_monitor_dashboard())
        except KeyboardInterrupt:
            console.print()
            console.print("[yellow]Monitoring watch stopped.[/yellow]")
            console.print()
    else:
        display_monitor_dashboard()


@app.command(name="resolve")
def resolve_system_alert(alert_id: str):
    """
    Resolve an active system alert by ID.
    """
    try:
        post(f"/monitor/alert/resolve/{alert_id}")
        console.print()
        console.print(f"[bold green]Success:[/bold green] Alert '{alert_id}' has been marked as resolved.")
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
