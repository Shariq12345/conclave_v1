import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, delete, to_policy, RemoteAPIError

app = typer.Typer(help="Define and manage governance policies")
console = Console()

@app.callback()
def callback():
    """
    Policy command group callback.
    """
    pass

@app.command(name="create")
def create_policy(
    name: str, 
    description: str = typer.Option("", "--description", "-d", help="Description of the policy rules."),
    secagg: bool = typer.Option(False, "--secagg", help="Enable Secure Aggregation (SecAgg)."),
    dp: bool = typer.Option(False, "--dp", help="Enable Differential Privacy (DP)."),
    epsilon: float = typer.Option(1.0, "--epsilon", help="Differential Privacy budget Epsilon."),
    delta: float = typer.Option(1e-5, "--delta", help="Differential Privacy budget Delta.")
):
    """
    Create a new governance policy.
    """
    try:
        data = post("/policies/create", {
            "name": name,
            "description": description,
            "secagg_enabled": secagg,
            "dp_enabled": dp,
            "dp_epsilon": epsilon,
            "dp_delta": delta
        })
        policy = to_policy(data)
        console.print()
        console.print(Panel(
            f"Policy Name   : [bold white]{policy.name}[/bold white]\n"
            f"ID            : [dim]{policy.id}[/dim]\n"
            f"Status        : [bold green]{policy.status}[/bold green]\n"
            f"Description   : {policy.description if policy.description else '[dim](None)[/dim]'}\n"
            f"SecAgg        : [bold]{'Enabled' if policy.secagg_enabled else 'Disabled'}[/bold]\n"
            f"Diff Privacy  : [bold]{'Enabled (Eps=' + str(policy.dp_epsilon) + ', Del=' + str(policy.dp_delta) + ')' if policy.dp_enabled else 'Disabled'}[/bold]\n"
            f"Created At    : {policy.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            title="[bold green]Success: Policy Created[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="list")
def list_policies():
    """
    List all governance policies.
    """
    try:
        data = get("/policies/list")
        policies = [to_policy(p) for p in data]
        
        if not policies:
            console.print()
            console.print("[yellow]No policies defined yet. Run [bold cyan]policy create <name>[/bold cyan] to create one.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Governance Policies[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2)
        )
        
        table.add_column("Policy Name", style="bold magenta")
        table.add_column("Status", style="bold green")
        table.add_column("Description", style="white")
        table.add_column("Created At", style="cyan")
        
        for p in policies:
            status_style = "bold green" if p.status == "Enabled" else "bold red"
            table.add_row(
                p.name,
                f"[{status_style}]{p.status}[/{status_style}]",
                p.description if p.description else "[dim](None)[/dim]",
                p.created_at.strftime("%Y-%m-%d %H:%M:%S")
            )
            
        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="show")
def show_policy(name: str):
    """
    Display detailed information for a specific policy.
    """
    try:
        data = get(f"/policies/show/{name}")
        policy = to_policy(data)
        status_style = "bold green" if policy.status == "Enabled" else "bold red"
        details = (
            f"[bold]Name          :[/bold] [bold white]{policy.name}[/bold white]\n"
            f"[bold]ID            :[/bold] [dim]{policy.id}[/dim]\n"
            f"[bold]Status        :[/bold] [{status_style}]{policy.status}[/{status_style}]\n"
            f"[bold]Description   :[/bold] {policy.description if policy.description else '[dim](None)[/dim]'}\n"
            f"[bold]Created At    :[/bold] {policy.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        console.print()
        console.print(Panel(
            details,
            title=f"[bold blue]Policy: {policy.name}[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="enable")
def enable_policy(name: str):
    """
    Enable a specific policy.
    """
    try:
        data = post(f"/policies/enable/{name}")
        policy = to_policy(data)
        console.print(f"[bold green]Success:[/bold green] Policy [bold white]'{policy.name}'[/bold white] is now [bold green]Enabled[/bold green].")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="disable")
def disable_policy(name: str):
    """
    Disable a specific policy.
    """
    try:
        data = post(f"/policies/disable/{name}")
        policy = to_policy(data)
        console.print(f"[bold green]Success:[/bold green] Policy [bold white]'{policy.name}'[/bold white] is now [bold red]Disabled[/bold red].")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="remove")
def remove_policy(name: str):
    """
    Remove a specific policy.
    """
    try:
        data = get(f"/policies/show/{name}")
        policy = to_policy(data)
        if typer.confirm(f"Are you sure you want to remove policy '{policy.name}'?"):
            delete(f"/policies/remove/{policy.name}")
            console.print(f"[bold green]Success:[/bold green] Policy [bold white]'{policy.name}'[/bold white] has been successfully removed.")
        else:
            console.print("[yellow]Operation aborted.[/yellow]")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
