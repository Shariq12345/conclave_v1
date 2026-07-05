import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, delete, to_organization, RemoteAPIError

app = typer.Typer(help="Manage participating organizations and members")
console = Console()

@app.callback()
def callback():
    """
    Organization command group callback.
    """
    pass

@app.command(name="create")
def create_organization(
    name: str,
    org_type: str = typer.Option(..., "--type", "-t", help="Organization type (e.g. Hospital, Bank, Research Lab)"),
    description: str = typer.Option("", "--description", "-d", help="Optional description of the organization")
):
    """
    Create a new participating organization.
    """
    try:
        data = post("/organizations/create", {
            "name": name,
            "organization_type": org_type,
            "description": description
        })
        org = to_organization(data)
        console.print()
        console.print(Panel(
            f"Organization Name : [bold white]{org.name}[/bold white]\n"
            f"ID                : [dim]{org.id}[/dim]\n"
            f"Type              : {org.organization_type}\n"
            f"Status            : [bold green]{org.status}[/bold green]\n"
            f"Description       : {org.description if org.description else '[dim](None)[/dim]'}\n"
            f"Created At        : {org.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            title="[bold green]Success: Organization Created[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="list")
def list_organizations():
    """
    List all participating organizations.
    """
    try:
        data = get("/organizations/list")
        orgs = [to_organization(o) for o in data]
        
        if not orgs:
            console.print()
            console.print("[yellow]No organizations registered yet. Run [bold cyan]organization create <name> --type <type>[/bold cyan] to register one.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Participating Organizations[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2)
        )
        
        table.add_column("Organization Name", style="bold magenta")
        table.add_column("Type", style="cyan")
        table.add_column("Status", style="bold green")
        table.add_column("Description", style="white")
        table.add_column("Created At", style="dim")
        
        for org in orgs:
            status_style = "bold green" if org.status == "Active" else "bold red"
            table.add_row(
                org.name,
                org.organization_type,
                f"[{status_style}]{org.status}[/{status_style}]",
                org.description if org.description else "[dim](None)[/dim]",
                org.created_at.strftime("%Y-%m-%d %H:%M:%S")
            )
            
        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="show")
def show_organization(name: str):
    """
    Display detailed information for a specific organization.
    """
    try:
        data = get(f"/organizations/show/{name}")
        org = to_organization(data)
        status_style = "bold green" if org.status == "Active" else "bold red"
        details = (
            f"[bold]Name        :[/bold] [bold white]{org.name}[/bold white]\n"
            f"[bold]ID          :[/bold] [dim]{org.id}[/dim]\n"
            f"[bold]Type        :[/bold] {org.organization_type}\n"
            f"[bold]Status      :[/bold] [{status_style}]{org.status}[/{status_style}]\n"
            f"[bold]Description :[/bold] {org.description if org.description else '[dim](None)[/dim]'}\n"
            f"[bold]Created At  :[/bold] {org.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"[bold]Updated At  :[/bold] {org.updated_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        console.print()
        console.print(Panel(
            details,
            title=f"[bold blue]Organization: {org.name}[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="update")
def update_organization(
    name: str,
    org_type: str = typer.Option(None, "--type", "-t", help="Updated organization type"),
    description: str = typer.Option(None, "--description", "-d", help="Updated organization description")
):
    """
    Update details for an existing organization.
    """
    try:
        data = post(f"/organizations/update/{name}", {
            "organization_type": org_type,
            "description": description
        })
        org = to_organization(data)
        console.print(f"[bold green]Success:[/bold green] Organization [bold white]'{org.name}'[/bold white] has been successfully updated.")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="deactivate")
def deactivate_organization(name: str):
    """
    Deactivate a specific organization.
    """
    try:
        data = post(f"/organizations/deactivate/{name}")
        org = to_organization(data)
        console.print(f"[bold green]Success:[/bold green] Organization [bold white]'{org.name}'[/bold white] is now [bold red]Inactive[/bold red].")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="remove")
def remove_organization(name: str):
    """
    Remove an organization configuration/record.
    """
    try:
        data = get(f"/organizations/show/{name}")
        org = to_organization(data)
        if typer.confirm(f"Are you sure you want to remove organization '{org.name}'?"):
            delete(f"/organizations/remove/{org.name}")
            console.print(f"[bold green]Success:[/bold green] Organization [bold white]'{org.name}'[/bold white] has been successfully removed.")
        else:
            console.print("[yellow]Operation aborted.[/yellow]")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
