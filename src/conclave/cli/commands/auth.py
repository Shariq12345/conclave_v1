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
    username_or_email: str = typer.Option(..., "--username", "-u", prompt="Username or Email", help="Username or Email address"),
    password: str = typer.Option(None, "--password", "-p", help="Optional password (bypasses prompt)")
):
    """
    Log in with your credentials to obtain a security token.
    """
    if not password:
        password = typer.prompt("Password", hide_input=True)
    try:
        data = post("/auth/login", {
            "username_or_email": username_or_email,
            "password": password
        })
        
        # Check if MFA is required
        if isinstance(data, dict) and data.get("pending_mfa"):
            console.print("[yellow]Multi-Factor Authentication (MFA) is enabled on this account.[/yellow]")
            mfa_token = data["mfa_token"]
            code = typer.prompt("Enter 6-digit authenticator app code or backup code")
            
            # Authenticate second factor
            mfa_res = post("/auth/login/mfa", {
                "mfa_token": mfa_token,
                "code": code
            })
            token = mfa_res["access_token"]
        else:
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


@app.command(name="forgot-password")
def forgot_password(
    username_or_email: str = typer.Option(..., "--username", "-u", prompt="Username or Email", help="Username or Email address")
):
    """
    Request a password reset link.
    """
    try:
        data = post("/auth/forgot-password", {
            "email_or_username": username_or_email
        })
        console.print(f"[bold green]Success:[/bold green] {data.get('message')}")
    except RemoteAPIError as e:
        console.print(f"[bold red]Request Failed:[/bold red] {e}")


@app.command(name="reset-password")
def reset_password(
    token: str = typer.Option(..., "--token", "-t", prompt="Reset Token", help="The reset token received in email"),
):
    """
    Reset your password using a reset token.
    """
    new_password = typer.prompt("Enter new password", hide_input=True)
    confirm = typer.prompt("Confirm new password", hide_input=True)
    if new_password != confirm:
        console.print("[bold red]Error:[/bold red] Passwords do not match.")
        raise typer.Exit(code=1)
        
    try:
        data = post("/auth/reset-password", {
            "token": token,
            "new_password": new_password
        })
        console.print(f"[bold green]Success:[/bold green] {data.get('message')}")
    except RemoteAPIError as e:
        console.print(f"[bold red]Reset Failed:[/bold red] {e}")


@app.command(name="mfa-setup")
def mfa_setup():
    """
    Initialize MFA registration.
    """
    try:
        data = post("/auth/mfa/setup", {})
        console.print()
        console.print(Panel(
            f"MFA Secret Key : [bold yellow]{data['secret']}[/bold yellow]\n"
            f"Provisioning URI: {data['otpauth_uri']}\n\n"
            "[bold white]Please add the Secret Key above to your authenticator app (e.g. Google Authenticator), "
            "then run [cyan]conclave auth mfa-confirm[/cyan] to activate MFA.[/bold white]",
            title="[bold blue]MFA Registration Initialized[/bold blue]",
            border_style="blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]MFA Setup Failed:[/bold red] {e}")


@app.command(name="mfa-confirm")
def mfa_confirm(
    secret: str = typer.Option(..., "--secret", "-s", prompt="MFA Secret Key", help="The MFA secret key generated by mfa-setup")
):
    """
    Confirm and activate MFA using a verification code.
    """
    code = typer.prompt("Enter 6-digit authenticator app code")
    try:
        data = post("/auth/mfa/confirm", {
            "secret": secret,
            "code": code
        })
        
        backup_codes = data.get("backup_codes", [])
        backup_text = "\n".join([f"  - {c}" for c in backup_codes])
        
        console.print()
        console.print(Panel(
            f"[bold green]MFA has been successfully enabled![/bold green]\n\n"
            f"[bold red]Emergency Backup Recovery Codes (Save these safely!):[/bold red]\n"
            f"[bold white]{backup_text}[/bold white]",
            title="[bold green]MFA Enabled[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]MFA Confirmation Failed:[/bold red] {e}")


@app.command(name="mfa-disable")
def mfa_disable():
    """
    Disable MFA on your account using a verification code.
    """
    code = typer.prompt("Enter 6-digit authenticator app code to confirm deactivation")
    try:
        data = post("/auth/mfa/disable", {
            "code": code
        })
        console.print(f"[bold green]Success:[/bold green] {data.get('message')}")
    except RemoteAPIError as e:
        console.print(f"[bold red]Failed to Disable MFA:[/bold red] {e}")
