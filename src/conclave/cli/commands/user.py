import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, delete, to_user, RemoteAPIError

app = typer.Typer(help="Manage users and accounts within organizations")
console = Console()

@app.callback()
def callback():
    """
    User command group callback.
    """
    pass

def _get_org_map():
    """Fetch org id→name map; silently return empty dict if unauthorized."""
    try:
        orgs_data = get("/organizations/list")
        return {o["id"]: o["name"] for o in orgs_data}
    except Exception:
        return {}

@app.command(name="create")
def create_user(
    username: str,
    org: str = typer.Option(..., "--org", "-o", help="Organization name to assign user to"),
    email: str = typer.Option(..., "--email", "-e", help="Unique email address for the user"),
    name: str = typer.Option(..., "--name", "-n", help="Full name of the user"),
    role: str = typer.Option("Operator", "--role", "-r", help="Role: 'System Admin', 'Organization Admin', 'Operator', 'Auditor'"),
):
    """
    Create a new user within an organization.
    """
    try:
        data = post("/users/create", {
            "username": username,
            "org_name": org,
            "email": email,
            "full_name": name,
            "role": role,
        })
        user = to_user(data)
        org_map = _get_org_map()
        console.print()
        console.print(Panel(
            f"Username      : [bold white]{user.username}[/bold white]\n"
            f"Full Name     : {user.full_name}\n"
            f"Email         : [bold magenta]{user.email}[/bold magenta]\n"
            f"Organization  : {org_map.get(user.organization_id, 'Unknown')}\n"
            f"Role          : [bold cyan]{user.role}[/bold cyan]\n"
            f"Status        : [bold green]{user.status}[/bold green]\n"
            f"Created At    : {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            title="[bold green]Success: User Created[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="list")
def list_users():
    """
    List all registered users.
    """
    try:
        data = get("/users/list")
        users = [to_user(u) for u in data]
        
        if not users:
            console.print()
            console.print("[yellow]No users registered yet. Run [bold cyan]user create <username> --org <org> --email <email> --name <name>[/bold cyan] to create one.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Registered Users[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2)
        )
        
        table.add_column("Username", style="bold magenta")
        table.add_column("Full Name", style="white")
        table.add_column("Email", style="bold white")
        table.add_column("Organization", style="cyan")
        table.add_column("Role", style="bright_cyan")
        table.add_column("Status", style="bold green")
        table.add_column("Created At", style="dim")
        
        org_map = _get_org_map()
        
        for u in users:
            status_style = "bold green" if u.status == "Active" else "bold red"
            table.add_row(
                u.username,
                u.full_name,
                u.email,
                org_map.get(u.organization_id, "Unknown"),
                u.role,
                f"[{status_style}]{u.status}[/{status_style}]",
                u.created_at.strftime("%Y-%m-%d %H:%M:%S")
            )
            
        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="show")
def show_user(username: str):
    """
    Display detailed information for a specific user.
    """
    try:
        data = get(f"/users/show/{username}")
        user = to_user(data)
        org_map = _get_org_map()
        status_style = "bold green" if user.status == "Active" else "bold red"
        details = (
            f"[bold]Username     :[/bold] [bold white]{user.username}[/bold white]\n"
            f"[bold]ID           :[/bold] [dim]{user.id}[/dim]\n"
            f"[bold]Full Name    :[/bold] {user.full_name}\n"
            f"[bold]Email        :[/bold] [bold magenta]{user.email}[/bold magenta]\n"
            f"[bold]Organization :[/bold] {org_map.get(user.organization_id, 'Unknown')}\n"
            f"[bold]Role         :[/bold] [bold cyan]{user.role}[/bold cyan]\n"
            f"[bold]Status       :[/bold] [{status_style}]{user.status}[/{status_style}]\n"
            f"[bold]Created At   :[/bold] {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"[bold]Updated At   :[/bold] {user.updated_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        console.print()
        console.print(Panel(
            details,
            title=f"[bold blue]User: {user.username}[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="update")
def update_user(
    username: str,
    email: str = typer.Option(None, "--email", "-e", help="Updated user email"),
    name: str = typer.Option(None, "--name", "-n", help="Updated user full name")
):
    """
    Update details for an existing user.
    """
    try:
        data = post(f"/users/update/{username}", {
            "email": email,
            "full_name": name
        })
        user = to_user(data)
        console.print(f"[bold green]Success:[/bold green] User [bold white]'{user.username}'[/bold white] has been successfully updated.")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="deactivate")
def deactivate_user(username: str):
    """
    Deactivate a specific user account.
    """
    try:
        data = post(f"/users/deactivate/{username}")
        user = to_user(data)
        console.print(f"[bold green]Success:[/bold green] User [bold white]'{user.username}'[/bold white] is now [bold red]Inactive[/bold red].")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="remove")
def remove_user(username: str):
    """
    Remove a user account.
    """
    try:
        data = get(f"/users/show/{username}")
        user = to_user(data)
        if typer.confirm(f"Are you sure you want to remove user '{user.username}'?"):
            delete(f"/users/remove/{user.username}")
            console.print(f"[bold green]Success:[/bold green] User [bold white]'{user.username}'[/bold white] has been successfully removed.")
        else:
            console.print("[yellow]Operation aborted.[/yellow]")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
