import typer
from rich.console import Console
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, RemoteAPIError

app = typer.Typer(help="Manage and view notifications and alerts")
console = Console()

@app.callback()
def callback():
    """
    Notification command group callback.
    """
    pass

@app.command(name="list")
def list_notifications():
    """
    List all notifications and alerts.
    """
    try:
        notifications = get("/notifications/list")
        if not notifications:
            console.print()
            console.print("[yellow]No notifications recorded yet.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Notifications & Alerts[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2)
        )
        
        table.add_column("ID", style="dim magenta")
        table.add_column("Type", style="cyan")
        table.add_column("Severity", style="bold")
        table.add_column("Title", style="bold white")
        table.add_column("Message", style="dim")
        table.add_column("Status", style="bold")
        
        for n in notifications:
            sev = n.get("severity", "Info")
            if sev == "Critical":
                sev_styled = f"[bold red]{sev}[/bold red]"
            elif sev == "Warning":
                sev_styled = f"[bold yellow]{sev}[/bold yellow]"
            else:
                sev_styled = f"[cyan]{sev}[/cyan]"
                
            is_read = n.get("read", False)
            status_styled = "[dim green]Read[/dim green]" if is_read else "[bold red]* Unread[/bold red]"
            row_style = "bold white" if not is_read else ""
            
            table.add_row(
                n.get("id")[:8],
                n.get("type"),
                sev_styled,
                n.get("title"),
                n.get("message"),
                status_styled,
                style=row_style
            )
            
        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="read")
def read_notification(notification_id: str):
    """
    Mark a specific notification as read.
    """
    try:
        post(f"/notifications/read/{notification_id}")
        console.print()
        console.print(f"[bold green]Success:[/bold green] Notification '{notification_id}' marked as read.")
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="read-all")
def read_all_notifications():
    """
    Mark all notifications as read.
    """
    try:
        res = post("/notifications/read-all")
        count = res.get("count", 0)
        console.print()
        console.print(f"[bold green]Success:[/bold green] Marked {count} notifications as read.")
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
