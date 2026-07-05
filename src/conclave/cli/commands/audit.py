import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, to_audit, RemoteAPIError

app = typer.Typer(help="Review activity logs and compliance reports")
console = Console()

@app.callback()
def callback():
    """
    Audit command group callback.
    """
    pass

@app.command(name="list")
def list_audits():
    """
    List all governance and system audit logs.
    """
    try:
        data = get("/audit/list")
        events = [to_audit(e) for e in data]
        
        if not events:
            console.print()
            console.print("[yellow]No audit logs recorded yet.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]System Audit Logs[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2)
        )
        
        table.add_column("Event ID", style="dim magenta")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Action", style="bold white")
        table.add_column("Resource", style="yellow")
        table.add_column("Status", style="bold")
        table.add_column("Message", style="dim")
        
        for event in events:
            status_style = "bold green" if event.status == "Success" else "bold red"
            table.add_row(
                event.id[:8],
                event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                event.action,
                f"{event.resource_type}: {event.resource_name}",
                f"[{status_style}]{event.status}[/{status_style}]",
                event.message
            )
            
        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="show")
def show_audit(event_id: str):
    """
    Show detailed information for a specific audit log entry.
    """
    try:
        data = get(f"/audit/show/{event_id}")
        event = to_audit(data)
        
        status_style = "bold green" if event.status == "Success" else "bold red"
        
        details = (
            f"[bold]Event ID      :[/bold] [dim]{event.id}[/dim]\n"
            f"[bold]Timestamp     :[/bold] {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"[bold]Event Type    :[/bold] [bold magenta]{event.event_type}[/bold magenta]\n"
            f"[bold]Resource Type :[/bold] {event.resource_type}\n"
            f"[bold]Resource Name :[/bold] [bold white]{event.resource_name}[/bold white]\n"
            f"[bold]Action        :[/bold] {event.action}\n"
            f"[bold]Status        :[/bold] [{status_style}]{event.status}[/{status_style}]\n"
            f"[bold]Message       :[/bold] {event.message}"
        )
        console.print()
        console.print(Panel(
            details,
            title=f"[bold blue]Audit Event: {event.event_type}[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="clear")
def clear_audits():
    """
    Clear all audit log entries.
    """
    try:
        if typer.confirm("Are you sure you want to remove all audit entries?"):
            post("/audit/clear")
            console.print()
            console.print("[bold green]Success:[/bold green] All audit entries removed.")
            console.print()
        else:
            console.print("[yellow]Operation aborted.[/yellow]")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="verify")
def verify_audit():
    """
    Verify the cryptographic integrity of the audit log ledger chain.
    """
    try:
        data = get("/audit/verify")
        status = data.get("status")
        
        console.print()
        if status == "Secure":
            blocks = data.get("verified_blocks", 0)
            panel_text = (
                f"Ledger Integrity Status : [bold green]Verified (Secure)[/bold green]\n"
                f"Total Audited Blocks    : [bold white]{blocks}[/bold white]\n"
                f"Chain Hash Link Status  : [bold green]Valid & Connected[/bold green]\n"
                f"Verification Timestamp  : {data.get('timestamp')}"
            )
            console.print(Panel(
                panel_text,
                title="[bold green]✔ Cryptographic Ledger Integrity Check Passed[/bold green]",
                border_style="green",
                expand=False,
                padding=(1, 3)
            ))
        else:
            error_msg = data.get("error", "Unknown tampering error")
            panel_text = (
                f"Ledger Integrity Status : [bold red]Compromised (Tampering Detected!)[/bold red]\n"
                f"Error Details           : [bold yellow]{error_msg}[/bold yellow]\n\n"
                f"[bold red]WARNING:[/bold red] The database audit records have been modified outside the Conclave application scope! Governance approval histories and policy states can no longer be trusted."
            )
            console.print(Panel(
                panel_text,
                title="[bold red]✘ SECURITY BREACH: Audit Chain Validation Failed[/bold red]",
                border_style="red",
                expand=False,
                padding=(1, 3)
            ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
