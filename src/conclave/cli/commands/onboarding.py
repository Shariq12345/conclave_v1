"""
conclave.cli.commands.onboarding
──────────────────────────────────
CLI commands for Org Admins to manage join requests.

onboarding pending          — list pending join requests for your org
onboarding approve <id>     — approve a join request
onboarding reject <id>      — reject a join request
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import get, post, RemoteAPIError

app = typer.Typer(help="Manage join requests for your organization")
console = Console()


@app.callback()
def callback():
    pass


@app.command(name="pending")
def list_pending():
    """List all pending join requests for your organization."""
    try:
        data = get("/onboarding/pending")

        if not data:
            console.print()
            console.print("[yellow]No pending join requests.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Pending Join Requests[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2),
        )
        table.add_column("ID (short)", style="dim", width=12)
        table.add_column("Username", style="bold magenta")
        table.add_column("Full Name", style="white")
        table.add_column("Email", style="bold white")
        table.add_column("Invite Code", style="bold yellow")
        table.add_column("Submitted", style="dim")

        for r in data:
            short_id = r["id"][:8] + "…"
            table.add_row(
                short_id,
                r["username"],
                r["full_name"],
                r["email"],
                r["invite_code"],
                r["created_at"][:19].replace("T", " "),
            )

        console.print()
        console.print(table)
        console.print()
        console.print(
            f"[dim]Use [bold cyan]onboarding approve <request-id>[/bold cyan] "
            f"or [bold cyan]onboarding reject <request-id>[/bold cyan] to review.[/dim]"
        )
        console.print()

    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="approve")
def approve_request(request_id: str):
    """Approve a pending join request. The user becomes an Operator."""
    try:
        data = post(f"/onboarding/approve/{request_id}")
        approved = data.get("approved_user", {})
        console.print()
        console.print(Panel(
            f"[bold white]Username  :[/bold white] [bold green]{approved.get('username')}[/bold green]\n"
            f"[bold white]Full Name :[/bold white] {approved.get('full_name')}\n"
            f"[bold white]Role      :[/bold white] [bold cyan]{approved.get('role')}[/bold cyan]\n"
            f"[bold white]Status    :[/bold white] [bold green]{approved.get('status')}[/bold green]\n\n"
            f"[dim]This user can now log in using [bold cyan]auth login[/bold cyan].[/dim]",
            title="[bold green]✔ Join Request Approved[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3),
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


@app.command(name="reject")
def reject_request(request_id: str):
    """Reject a pending join request."""
    try:
        if not typer.confirm(f"Reject join request '{request_id[:8]}…'?"):
            console.print("[yellow]Aborted.[/yellow]")
            return
        data = post(f"/onboarding/reject/{request_id}")
        req = data.get("join_request", {})
        console.print(
            f"[bold green]Done:[/bold green] Join request for "
            f"[bold white]'{req.get('username')}'[/bold white] has been rejected."
        )
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
