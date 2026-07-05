import typer
from rich.console import Console
from rich.panel import Panel
import os
from conclave.cli.client import post, get, RemoteAPIError, to_user, TOKEN_FILE

app = typer.Typer(help="Authenticate and manage user sessions")
console = Console()

@app.callback()
def callback():
    """
    Auth command group callback.
    """
    pass

@app.command(name="register")
def register_user(
    username: str = typer.Argument(..., help="Desired username"),
    org: str = typer.Option(..., "--org", "-o", help="Organization name to assign user to"),
    email: str = typer.Option(..., "--email", "-e", help="Unique email address for the user"),
    name: str = typer.Option(..., "--name", "-n", help="Full name of the user")
):
    """
    Register a new user with a password.
    """
    password = typer.prompt("Enter password", hide_input=True)
    confirm = typer.prompt("Confirm password", hide_input=True)
    if password != confirm:
        console.print("[bold red]Error:[/bold red] Passwords do not match.")
        raise typer.Exit(code=1)
        
    try:
        data = post("/auth/register", {
            "username": username,
            "org_name": org,
            "email": email,
            "full_name": name,
            "password": password
        })
        user = to_user(data)
        console.print()
        console.print(Panel(
            f"Username     : [bold white]{user.username}[/bold white]\n"
            f"Full Name    : {user.full_name}\n"
            f"Email        : [bold magenta]{user.email}[/bold magenta]\n"
            f"Status       : [bold green]{user.status}[/bold green]\n\n"
            f"[bold green]Registered successfully! You can now login using:[/bold green]\n"
            f"[bold cyan]auth login --username {user.username}[/bold cyan]",
            title="[bold green]Registration Success[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="login")
def login(
    username_or_email: str = typer.Option(..., "--username", "-u", prompt="Username or Email", help="Username or Email address")
):
    """
    Log in with your credentials to obtain a security token.
    """
    password = typer.prompt("Password", hide_input=True)
    try:
        data = post("/auth/login", {
            "username_or_email": username_or_email,
            "password": password
        })
        token = data["access_token"]
        
        # Save token locally
        with open(TOKEN_FILE, "w") as f:
            f.write(token)
            
        console.print("[bold green]Success:[/bold green] Logged in successfully. Token stored locally.")
    except RemoteAPIError as e:
        console.print(f"[bold red]Login Failed:[/bold red] {e}")

@app.command(name="logout")
def logout():
    """
    Log out and clear stored session credentials.
    """
    if os.path.exists(TOKEN_FILE):
        try:
            os.remove(TOKEN_FILE)
            console.print("[bold green]Success:[/bold green] Logged out. Token removed.")
        except Exception as e:
            console.print(f"[bold red]Error clearing session:[/bold red] {e}")
    else:
        console.print("[yellow]You are not logged in.[/yellow]")

@app.command(name="whoami")
def whoami():
    """
    Display details of the currently authenticated user session.
    """
    try:
        data = get("/auth/whoami")
        user = to_user(data)
        
        # Resolve org map if possible
        try:
            orgs_data = get("/organizations/list")
            org_map = {o["id"]: o["name"] for o in orgs_data}
        except Exception:
            org_map = {}
            
        status_style = "bold green" if user.status == "Active" else "bold red"
        details = (
            f"[bold]Username     :[/bold] [bold white]{user.username}[/bold white]\n"
            f"[bold]Full Name    :[/bold] {user.full_name}\n"
            f"[bold]Email        :[/bold] [bold magenta]{user.email}[/bold magenta]\n"
            f"[bold]Organization :[/bold] {org_map.get(user.organization_id, 'Unknown')}\n"
            f"[bold]Status       :[/bold] [{status_style}]{user.status}[/{status_style}]\n"
            f"[bold]Last Login   :[/bold] {user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'Never'}"
        )
        console.print()
        console.print(Panel(
            details,
            title="[bold blue]Current Session Identity (whoami)[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
