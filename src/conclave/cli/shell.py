import os
import shlex
import click
import typer
import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.prompt import Prompt, Confirm
from rich import box
from conclave import __version__

console = Console()

# ── Helpers ────────────────────────────────────────────────────────────────────

def _server_url() -> str:
    from conclave.cli.config import load_server_url
    return load_server_url()


def _save_token(token: str) -> None:
    from conclave.cli.client import TOKEN_FILE
    with open(TOKEN_FILE, "w") as f:
        f.write(token)


def _get_onboarding_status() -> dict | None:
    """Call GET /onboarding/status. Returns None if server is unreachable."""
    try:
        r = requests.get(f"{_server_url()}/onboarding/status", timeout=4)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _prompt_password(label: str = "Password") -> str:
    """Prompt for a password twice and confirm they match."""
    while True:
        pw = Prompt.ask(f"  [bold cyan]{label}[/bold cyan]", password=True, console=console)
        confirm = Prompt.ask("  [bold cyan]Confirm password[/bold cyan]", password=True, console=console)
        if pw == confirm:
            return pw
        console.print("  [bold red]Passwords do not match. Please try again.[/bold red]")


# ── Onboarding wizard ──────────────────────────────────────────────────────────

def _print_onboarding_banner():
    console.print()
    console.print(Panel(
        Text.assemble(
            Text("Welcome to Conclave!\n\n", style="bold bright_white"),
            Text("It looks like this is your first time.\n", style="dim white"),
            Text("Let's get you set up in just a few steps.", style="italic white"),
        ),
        title="[bold yellow]✦ First-Time Setup[/bold yellow]",
        border_style="bright_blue",
        expand=False,
        padding=(1, 4),
    ))
    console.print()


def _scenario_create_org() -> bool:
    """Scenario 1: Create a new organization and become its admin."""
    import questionary
    console.print()
    console.print(Rule("[bold cyan]Create a New Organization[/bold cyan]", style="bright_blue"))
    console.print("[dim]You will become the Organization Admin for this new organization.[/dim]")
    console.print()

    org_name = questionary.text("Organization name:").ask()
    if not org_name:
        return False
    org_type = questionary.select(
        "Organization type:",
        choices=["Hospital", "Bank", "Research Lab", "University", "Government", "Other"],
        default="Hospital"
    ).ask()
    if not org_type:
        return False
    
    username = questionary.text("Admin username:").ask()
    if not username:
        return False
    full_name = questionary.text("Full name:").ask()
    if not full_name:
        return False
    email = questionary.text("Email address:").ask()
    if not email:
        return False
    
    password = questionary.password("Password:").ask()
    if not password:
        return False
    confirm = questionary.password("Confirm password:").ask()
    if password != confirm:
        console.print("[bold red]Error:[/bold red] Passwords do not match.")
        return False

    console.print()
    with console.status("[bold cyan]Creating your organization…[/bold cyan]"):
        try:
            r = requests.post(
                f"{_server_url()}/onboarding/create",
                json={
                    "org_name": org_name,
                    "org_type": org_type,
                    "username": username,
                    "email": email,
                    "full_name": full_name,
                    "password": password,
                },
                timeout=10,
            )
        except Exception as e:
            console.print(f"[bold red]Connection error:[/bold red] {e}")
            return False

    if r.status_code == 200:
        data = r.json()
        token = data.get("access_token")
        user  = data.get("user", {})
        org   = data.get("organization", {})
        _save_token(token)
        console.print()
        console.print(Panel(
            f"[bold white]Organization:[/bold white] [bold green]{org.get('name')}[/bold green]\n"
            f"[bold white]Username    :[/bold white] {user.get('username')}\n"
            f"[bold white]Role        :[/bold white] [bold cyan]{user.get('role')}[/bold cyan]\n"
            f"[bold white]Status      :[/bold white] [bold green]{user.get('status')}[/bold green]\n\n"
            f"[dim]You are now logged in. Welcome to Conclave![/dim]",
            title="[bold green]✔ Organization Created[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3),
        ))
        console.print()
        return True
    else:
        detail = r.json().get("detail", "Unknown error")
        console.print(f"[bold red]Error:[/bold red] {detail}")
        return False


def _scenario_join_org() -> bool:
    """Scenario 2: Join an existing organization (creates a pending join request)."""
    import questionary
    console.print()
    console.print(Rule("[bold cyan]Join an Existing Organization[/bold cyan]", style="bright_blue"))
    console.print("[dim]Your request will be reviewed by the Organization Admin before you can log in.[/dim]")
    console.print()

    org_name = questionary.text("Organization name:").ask()
    if not org_name:
        return False
    username = questionary.text("Choose a username:").ask()
    if not username:
        return False
    full_name = questionary.text("Full name:").ask()
    if not full_name:
        return False
    email = questionary.text("Email address:").ask()
    if not email:
        return False
    password = questionary.password("Password:").ask()
    if not password:
        return False
    confirm = questionary.password("Confirm password:").ask()
    if password != confirm:
        console.print("[bold red]Error:[/bold red] Passwords do not match.")
        return False

    console.print()
    with console.status("[bold cyan]Submitting your join request…[/bold cyan]"):
        try:
            r = requests.post(
                f"{_server_url()}/onboarding/join",
                json={
                    "org_name": org_name,
                    "username": username,
                    "email": email,
                    "full_name": full_name,
                    "password": password,
                },
                timeout=10,
            )
        except Exception as e:
            console.print(f"[bold red]Connection error:[/bold red] {e}")
            return False

    if r.status_code == 200:
        data     = r.json()
        req      = data.get("join_request", {})
        inv_code = req.get("invite_code", "—")
        console.print()
        console.print(Panel(
            f"[bold white]Organization :[/bold white] {org_name}\n"
            f"[bold white]Username     :[/bold white] {username}\n"
            f"[bold white]Invite Code  :[/bold white] [bold yellow]{inv_code}[/bold yellow]\n"
            f"[bold white]Status       :[/bold white] [dim]Pending Approval[/dim]\n\n"
            f"[dim]Share your invite code with the Organization Admin.\n"
            f"Once approved, run [bold cyan]auth login[/bold cyan] to access Conclave.[/dim]",
            title="[bold yellow]⏳ Join Request Submitted[/bold yellow]",
            border_style="yellow",
            expand=False,
            padding=(1, 3),
        ))
        console.print()
        return False   # Cannot enter REPL yet — must wait for approval
    else:
        detail = r.json().get("detail", "Unknown error")
        console.print(f"[bold red]Error:[/bold red] {detail}")
        return False


def _scenario_connect_server() -> bool:
    """Scenario 3: Point the CLI at an existing Conclave server."""
    import questionary
    console.print()
    console.print(Rule("[bold cyan]Connect to an Existing Server[/bold cyan]", style="bright_blue"))
    console.print("[dim]Enter the address of the Conclave Server your organization is running.[/dim]")
    console.print()

    current = _server_url()
    url = questionary.text("Server URL:", default=current).ask()
    if not url:
        return False
    url = url.rstrip("/")

    with console.status("[bold cyan]Connecting…[/bold cyan]"):
        try:
            r = requests.get(f"{url}/onboarding/status", timeout=4)
        except Exception as e:
            console.print(f"  [bold red]Could not connect to {url}:[/bold red] {e}")
            return False

    if r.status_code != 200:
        console.print(f"  [bold red]Unexpected response from server ({r.status_code}). Is it a Conclave server?[/bold red]")
        return False

    from conclave.cli.config import save_server_url
    save_server_url(url)

    status = r.json()
    console.print()
    console.print(Panel(
        f"[bold white]Server       :[/bold white] [bold green]{url}[/bold green]\n"
        f"[bold white]Initialized  :[/bold white] {'Yes' if status.get('initialized') else 'No'}\n"
        f"[bold white]Organizations:[/bold white] {status.get('org_count', 0)}\n\n"
        f"[dim]Run [bold cyan]auth login[/bold cyan] to authenticate with your credentials.[/dim]",
        title="[bold green]✔ Server Connected[/bold green]",
        border_style="green",
        expand=False,
        padding=(1, 3),
    ))
    console.print()
    return True   # Enter REPL (user will run auth login)


def _run_onboarding_wizard() -> bool:
    """
    Entry point for the first-time setup wizard.
    Returns True if the user should enter the REPL, False if not.
    """
    _print_onboarding_banner()
    import questionary

    choice = questionary.select(
        "First-Time Onboarding Wizard — Choose an option:",
        choices=[
            questionary.Choice("Create Organization (Start fresh — create a new org and become its admin)", value="1"),
            questionary.Choice("Join Organization (Request to join an existing org)", value="2"),
            questionary.Choice("Connect to Server (Point the CLI at an existing Conclave deployment)", value="3"),
        ]
    ).ask()

    if choice == "1":
        return _scenario_create_org()
    elif choice == "2":
        _scenario_join_org()
        return False
    elif choice == "3":
        _scenario_connect_server()
        # After connecting, re-check status
        status = _get_onboarding_status()
        if status and status.get("initialized"):
            console.print("[dim]Server is set up. Entering REPL — run [bold cyan]auth login[/bold cyan] to authenticate.[/dim]")
            return True
        elif status and not status.get("initialized"):
            # Server exists but has no orgs yet — show wizard again
            console.print()
            console.print("[dim]The connected server has no organizations yet. Let's set one up.[/dim]")
            return _run_onboarding_wizard()
        return True


# ── Welcome screen ─────────────────────────────────────────────────────────────

def display_welcome_screen():
    ascii_art = (
        "  ____             _                     \n"
        " / ___|___  _ __   ___| | __ ___   _____ \n"
        "| |   / _ \\| '_ \\ / __| |/ _` \\ \\ / / _ \\\n"
        "| |__| (_) | | | | (__| | (_| |\\ V /  __/\n"
        " \\____\\___/|_| |_|\\___|_|\\__,_| \\_/ \\___|\n"
        f"                              v{__version__}"
    )

    banner_text = Text(ascii_art, style="bold cyan")
    header_panel = Panel(
        Text.assemble(banner_text),
        expand=False,
        border_style="bright_blue",
        title="[bold yellow]Welcome to",
        title_align="center",
        padding=(1, 4),
    )

    console.print()
    console.print(header_panel)
    console.print()

    table = Table(
        title="[bold bright_white]Available Command Groups[/bold bright_white]",
        title_justify="left",
        box=None,
        show_header=True,
        header_style="bold bright_blue",
        padding=(0, 2),
    )

    table.add_column("Command Group", style="bold magenta", width=15)
    table.add_column("Description", style="white")
    table.add_column("Example Usage", style="dim green")

    table.add_row("auth",         "Authenticate and manage user sessions",           "auth login")
    table.add_row("organization", "Manage participating organizations and members",  "organization list")
    table.add_row("user",         "Manage users and accounts within organizations",  "user list")
    table.add_row("node",         "Register and manage federated learning nodes",    "node list")
    table.add_row("client",       "Manage federated learning clients and nodes",     "client list")
    table.add_row("policy",       "Define and enforce governance rules",             "policy validate")
    table.add_row("consent",      "Handle user data consent and agreements",         "consent verify")
    table.add_row("training",     "Orchestrate federated training sessions",         "training start")
    table.add_row("audit",        "Review activity logs and compliance reports",     "audit list")
    table.add_row("onboarding",   "Manage join requests for your organization",      "onboarding pending")
    table.add_row("help",         "Show this help screen or command-specific help",  "help [command]")

    console.print(table)
    console.print()
    console.print("[dim]Tip: Run [bold cyan][command] --help[/bold cyan] or [bold cyan]help [command][/bold cyan] to learn more.[/dim]")
    console.print()


# ── REPL ───────────────────────────────────────────────────────────────────────

def run_shell(app: typer.Typer):
    click_command = typer.main.get_command(app)
    ctx = click.Context(click_command)
    app_commands = click_command.list_commands(ctx)

    builtins = ["help", "version", "clear", "exit", "quit"]
    all_valid_commands = set(builtins + app_commands)

    # ── First-time onboarding check ───────────────────────────────────────────
    status = _get_onboarding_status()

    if status is None:
        # Server is unreachable — offer to connect to a different one
        console.print()
        console.print(Panel(
            "[bold white]Cannot reach the Conclave Server.[/bold white]\n\n"
            f"[dim]Tried: [bold]{_server_url()}[/bold]\n\n"
            "You can:\n"
            "  • Start the server: [bold cyan]conclave-server[/bold cyan]\n"
            "  • Or connect to an existing server.[/dim]",
            title="[bold red]⚠ Server Unreachable[/bold red]",
            border_style="red",
            expand=False,
            padding=(1, 3),
        ))
        console.print()
        if Confirm.ask("  Connect to a different server?", console=console, default=False):
            _scenario_connect_server()
            status = _get_onboarding_status()
            if status is None:
                console.print("[dim]Still unreachable. Entering offline REPL — some commands will fail.[/dim]")
        else:
            console.print("[dim]Entering offline REPL — some commands will fail until the server is running.[/dim]")

    elif not status.get("initialized"):
        # Fresh server — run the wizard
        should_continue = _run_onboarding_wizard()
        if not should_continue:
            console.print("[yellow]Exiting Conclave. Run [bold cyan]conclave[/bold cyan] again once your admin approves you.[/yellow]")
            return

    # ── Normal REPL ───────────────────────────────────────────────────────────
    is_interactive = True
    try:
        completer = WordCompleter(list(all_valid_commands), ignore_case=True)
        session = PromptSession(history=InMemoryHistory(), completer=completer)
    except Exception:
        is_interactive = False
        session = None

    display_welcome_screen()

    while True:
        try:
            if is_interactive and session is not None:
                text = session.prompt("conclave> ")
            else:
                text = input("conclave> ")
            text = text.strip()
            if not text:
                continue

            try:
                args = shlex.split(text)
            except ValueError as e:
                console.print(f"[bold red]Error parsing input:[/bold red] {e}")
                continue

            cmd = args[0]
            cmd_lower = cmd.lower()

            if cmd_lower not in all_valid_commands:
                console.print(
                    f"[bold red]Error:[/bold red] Unknown command '[bold]{cmd}[/bold]'. "
                    f"Type [bold cyan]help[/bold cyan] to see available commands."
                )
                continue

            if cmd_lower in ("exit", "quit"):
                console.print("[yellow]Exiting Conclave. Goodbye![/yellow]")
                break

            elif cmd_lower == "clear":
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            elif cmd_lower == "version":
                console.print(f"Conclave version [bold green]v{__version__}[/bold green]")
                continue

            elif cmd_lower == "help" and len(args) == 1:
                display_welcome_screen()
                continue

            if cmd_lower == "help" and len(args) > 1:
                sub_cmd = args[1]
                if sub_cmd in app_commands:
                    args = [sub_cmd, "--help"]
                else:
                    console.print(
                        f"[bold red]Error:[/bold red] Unknown command '[bold]{sub_cmd}[/bold]'. "
                        f"Type [bold cyan]help[/bold cyan] to see available commands."
                    )
                    continue

            try:
                click_command.main(args=args, standalone_mode=False)
            except click.exceptions.Exit:
                pass
            except click.exceptions.Abort:
                console.print("[yellow]Command aborted.[/yellow]")
            except click.NoSuchCommand as e:
                console.print(
                    f"[bold red]Error:[/bold red] Unknown command '[bold]{e.command}[/bold]'. "
                    f"Type [bold cyan]help[/bold cyan] to see available commands."
                )
            except click.ClickException as e:
                e.show()
            except Exception as e:
                console.print(f"[bold red]Internal Error:[/bold red] {e}")

        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting Conclave. Goodbye![/yellow]")
            break
