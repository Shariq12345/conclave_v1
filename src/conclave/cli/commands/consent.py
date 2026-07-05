import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, to_consent, to_client, RemoteAPIError

app = typer.Typer(help="Handle dataset usage consent and agreements")
console = Console()

@app.callback()
def callback():
    """
    Consent command group callback.
    """
    pass

@app.command(name="grant")
def grant_consent(client: str, dataset: str):
    """
    Grant consent for a client to use a specific dataset.
    """
    try:
        consent_data = post("/consents/grant", {"client_name": client, "dataset_name": dataset})
        consent = to_consent(consent_data)
        client_data = get(f"/clients/show/{client}")
        client_obj = to_client(client_data)
        console.print()
        console.print(Panel(
            f"Client Name   : [bold white]{client_obj.name}[/bold white]\n"
            f"Dataset       : [bold magenta]{consent.dataset_name}[/bold magenta]\n"
            f"Status        : [bold green]{consent.status}[/bold green]\n"
            f"Granted At    : {consent.granted_at.strftime('%Y-%m-%d %H:%M:%S')}",
            title="[bold green]Success: Consent Granted[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="revoke")
def revoke_consent(client: str, dataset: str):
    """
    Revoke consent for a client to use a specific dataset.
    """
    try:
        consent_data = post("/consents/revoke", {"client_name": client, "dataset_name": dataset})
        consent = to_consent(consent_data)
        client_data = get(f"/clients/show/{client}")
        client_obj = to_client(client_data)
        console.print(f"[bold green]Success:[/bold green] Consent for client [bold white]'{client_obj.name}'[/bold white] to use dataset [bold magenta]'{consent.dataset_name}'[/bold magenta] has been [bold red]Revoked[/bold red].")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="list")
def list_consents():
    """
    List all consent agreements.
    """
    try:
        consents_data = get("/consents/list")
        consents = [to_consent(c) for c in consents_data]
        
        if not consents:
            console.print()
            console.print("[yellow]No consent agreements defined yet. Run [bold cyan]consent grant <client> <dataset>[/bold cyan] to grant one.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Dataset Consent Agreements[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2)
        )
        
        table.add_column("Client Name", style="bold white")
        table.add_column("Dataset Name", style="bold magenta")
        table.add_column("Status", style="bold green")
        table.add_column("Granted At", style="cyan")
        table.add_column("Revoked At", style="dim cyan")
        
        clients_data = get("/clients/list")
        client_map = {c["id"]: c["name"] for c in clients_data}
        
        for c in consents:
            status_style = "bold green" if c.status == "Granted" else "bold red"
            client_name = client_map.get(c.client_id, "Unknown")
            revoked_str = c.revoked_at.strftime("%Y-%m-%d %H:%M:%S") if c.revoked_at else "-"
            
            table.add_row(
                client_name,
                c.dataset_name,
                f"[{status_style}]{c.status}[/{status_style}]",
                c.granted_at.strftime("%Y-%m-%d %H:%M:%S"),
                revoked_str
            )
            
        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="show")
def show_consents(client: str):
    """
    Show all consent agreements for a specific client.
    """
    try:
        client_data = get(f"/clients/show/{client}")
        client_obj = to_client(client_data)
        
        consents_data = get(f"/consents/show/{client}")
        consents = [to_consent(c) for c in consents_data]
        
        if not consents:
            console.print()
            console.print(f"[yellow]No consent agreements found for client [bold white]'{client_obj.name}'[/bold white].[/yellow]")
            console.print()
            return
            
        details = f"[bold cyan]Consent Rules for Client: {client_obj.name}[/bold cyan]\n\n"
        for i, c in enumerate(consents, 1):
            status_style = "bold green" if c.status == "Granted" else "bold red"
            details += (
                f"{i}. Dataset: [bold white]{c.dataset_name}[/bold white]\n"
                f"   Status:  [{status_style}]{c.status}[/{status_style}]\n"
                f"   Granted: {c.granted_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            if c.revoked_at:
                details += f"   Revoked: {c.revoked_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            details += "\n"
            
        console.print()
        console.print(Panel(
            details.strip(),
            title=f"[bold blue]Consent: {client_obj.name}[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
