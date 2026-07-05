import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, delete, to_client, RemoteAPIError

app = typer.Typer(help="Manage federated learning clients and nodes")
console = Console()

@app.callback()
def callback():
    """
    Client command group callback.
    """
    pass

@app.command(name="register")
def register_client(name: str):
    """
    Register a new client node (e.g., hospital, bank, research institute).
    """
    try:
        data = post("/clients/register", {"name": name})
        client = to_client(data)
        console.print()
        console.print(Panel(
            f"Client Name   : [bold white]{client.name}[/bold white]\n"
            f"ID            : [dim]{client.id}[/dim]\n"
            f"Status        : [bold green]{client.status}[/bold green]\n"
            f"Registered At : {client.registered_at.strftime('%Y-%m-%d %H:%M:%S')}",
            title="[bold green]Success: Client Registered[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="list")
def list_clients():
    """
    List all registered client nodes.
    """
    try:
        data = get("/clients/list")
        clients = [to_client(c) for c in data]
        
        if not clients:
            console.print()
            console.print("[yellow]No clients registered yet. Run [bold cyan]client register <name>[/bold cyan] to register one.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Registered Clients[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2)
        )
        
        table.add_column("Client ID", style="dim", width=38)
        table.add_column("Name", style="bold magenta")
        table.add_column("Status", style="bold green")
        table.add_column("Registered At", style="cyan")
        
        for client in clients:
            status_style = "bold green" if client.status == "Active" else "bold yellow"
            table.add_row(
                client.id,
                client.name,
                f"[{status_style}]{client.status}[/{status_style}]",
                client.registered_at.strftime("%Y-%m-%d %H:%M:%S")
            )
            
        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="show")
def show_client(name: str):
    """
    Show detailed information for a specific client node.
    """
    try:
        data = get(f"/clients/show/{name}")
        client = to_client(data)
        details = (
            f"[bold]Name          :[/bold] [bold white]{client.name}[/bold white]\n"
            f"[bold]ID            :[/bold] [dim]{client.id}[/dim]\n"
            f"[bold]Status        :[/bold] [bold green]{client.status}[/bold green]\n"
            f"[bold]Registered At :[/bold] {client.registered_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        console.print()
        console.print(Panel(
            details,
            title=f"[bold blue]Client: {client.name}[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="remove")
def remove_client(name: str):
    """
    Remove a client node from the system.
    """
    try:
        data = get(f"/clients/show/{name}")
        client = to_client(data)
        if typer.confirm(f"Are you sure you want to remove client '{client.name}'?"):
            delete(f"/clients/remove/{client.name}")
            console.print(f"[bold green]Success:[/bold green] Client [bold white]'{client.name}'[/bold white] has been successfully removed.")
        else:
            console.print("[yellow]Operation aborted.[/yellow]")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
