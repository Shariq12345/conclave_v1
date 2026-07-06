import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from conclave.cli.client import post, get, delete, to_training, RemoteAPIError

app = typer.Typer(help="Orchestrate federated training jobs")
console = Console()

@app.callback()
def callback():
    """
    Training command group callback.
    """
    pass

@app.command(name="create")
def create_training(
    name: str,
    clients: str = typer.Option(..., "--clients", help="Comma-separated list of participating client names"),
    policy: str = typer.Option(..., "--policy", help="Governance policy name"),
    dataset: str = typer.Option(..., "--dataset", help="Target dataset name"),
    description: str = typer.Option("", "--description", help="Optional description of the training session"),
    priority: str = typer.Option("Medium", "--priority", help="Priority of the training session (Low, Medium, High)")
):
    """
    Configure a new federated learning training session governed by a policy.
    """
    client_list = [c.strip() for c in clients.split(",") if c.strip()]
    try:
        data = post("/trainings/create", {
            "name": name,
            "participating_clients": client_list,
            "assigned_policy": policy,
            "dataset_name": dataset,
            "description": description,
            "priority": priority
        })
        session = to_training(data)
        console.print()
        console.print(Panel(
            f"Session Name  : [bold white]{session.name}[/bold white]\n"
            f"ID            : [dim]{session.id}[/dim]\n"
            f"Status        : [bold yellow]{session.status}[/bold yellow]\n"
            f"Priority      : [bold cyan]{session.priority}[/bold cyan]\n"
            f"Policy        : {session.assigned_policy}\n"
            f"Dataset       : {session.dataset_name}\n"
            f"Clients       : {', '.join(session.participating_clients)}\n"
            f"Created At    : {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            title="[bold green]Success: Training Session Configured[/bold green]",
            border_style="green",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="list")
def list_trainings():
    """
    List all configured federated training sessions.
    """
    try:
        data = get("/trainings/list")
        sessions = [to_training(s) for s in data]
        
        if not sessions:
            console.print()
            console.print("[yellow]No training sessions configured yet. Run [bold cyan]training create <name> --clients <clients> --policy <policy> --dataset <dataset>[/bold cyan] to create one.[/yellow]")
            console.print()
            return

        table = Table(
            title="[bold white]Configured Training Sessions[/bold white]",
            title_justify="left",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold bright_blue",
            padding=(0, 2)
        )
        
        table.add_column("Session ID", style="dim", width=38)
        table.add_column("Name", style="bold magenta")
        table.add_column("Status", style="bold yellow")
        table.add_column("Assigned Policy", style="cyan")
        table.add_column("Dataset", style="green")
        
        for session in sessions:
            status_style = "bold yellow"
            if session.status == "Running":
                status_style = "bold green"
            elif session.status == "Completed":
                status_style = "bold blue"
            elif session.status == "Failed":
                status_style = "bold red"
            elif session.status == "Stopped":
                status_style = "bold red"
                
            table.add_row(
                session.id,
                session.name,
                f"[{status_style}]{session.status}[/{status_style}]",
                session.assigned_policy,
                session.dataset_name
            )
            
        console.print()
        console.print(table)
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="show")
def show_training(name: str):
    """
    Show detailed information for a specific training session.
    """
    try:
        data = get(f"/trainings/show/{name}")
        session = to_training(data)
        
        status_style = "bold yellow"
        if session.status == "Running":
            status_style = "bold green"
        elif session.status == "Completed":
            status_style = "bold blue"
        elif session.status == "Failed":
            status_style = "bold red"
        elif session.status == "Stopped":
            status_style = "bold red"

        started_str = session.started_at.strftime('%Y-%m-%d %H:%M:%S') if session.started_at else "Not started"
        completed_str = session.completed_at.strftime('%Y-%m-%d %H:%M:%S') if session.completed_at else "Active / Interrupted"
        
        details = (
            f"[bold]Name          :[/bold] [bold white]{session.name}[/bold white]\n"
            f"[bold]ID            :[/bold] [dim]{session.id}[/dim]\n"
            f"[bold]Status        :[/bold] [{status_style}]{session.status}[/{status_style}]\n"
            f"[bold]Policy        :[/bold] {session.assigned_policy}\n"
            f"[bold]Dataset       :[/bold] {session.dataset_name}\n"
            f"[bold]Clients       :[/bold] {', '.join(session.participating_clients)}\n"
            f"[bold]Description   :[/bold] {session.description or 'No description'}\n"
            f"[bold]Created At    :[/bold] {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"[bold]Started At    :[/bold] {started_str}\n"
            f"[bold]Completed At  :[/bold] {completed_str}"
        )
        console.print()
        console.print(Panel(
            details,
            title=f"[bold blue]Training Session: {session.name}[/bold blue]",
            border_style="bright_blue",
            expand=False,
            padding=(1, 3)
        ))
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="start")
def start_training(name: str):
    """
    Start a governance-validated federated learning session.
    """
    import sys
    try:
        "✓".encode(sys.stdout.encoding or 'ascii')
        "✗".encode(sys.stdout.encoding or 'ascii')
        check_marker = "✓"
        cross_marker = "✗"
    except Exception:
        check_marker = "OK"
        cross_marker = "FAIL"

    try:
        data = post(f"/trainings/start/{name}")
        session_data = data["session"]
        val_result_data = data["validation_result"]
        
        console.print()
        console.print("[bold white]Governance Validation[/bold white]\n")
        for check in val_result_data.get("checks", []):
            check_passed = check.get("passed", False)
            check_name = check.get("name", "")
            if check_passed:
                console.print(f"  [green]{check_marker}[/green] {check_name}")
            else:
                console.print(f"  [red]{cross_marker}[/red] {check_name}")
        console.print("\nResult: [bold green]PASSED[/bold green]\n")
        console.print("[bold white]Starting Federated Learning Training...[/bold white]")
        console.print("[dim]Flower training server initiated in background. Track progress with 'monitor status'.[/dim]")
        console.print()
    except RemoteAPIError as e:
        console.print()
        console.print("[bold white]Governance Validation[/bold white]\n")
        if e.validation_result:
            for check in e.validation_result.get("checks", []):
                check_passed = check.get("passed", False)
                check_name = check.get("name", "")
                check_msg = check.get("message", "")
                if check_passed:
                    console.print(f"  [green]{check_marker}[/green] {check_name}")
                else:
                    console.print(f"  [red]{cross_marker}[/red] {check_name} - [dim]{check_msg}[/dim]")
            console.print("\nResult: [bold red]FAILED[/bold red]")
            console.print(f"[bold red]Error Details:[/bold red] {e}\n")
        else:
            console.print(f"[bold red]Error:[/bold red] {e}")
        console.print()

@app.command(name="stop")
def stop_training(name: str):
    """
    Stop a running training session.
    """
    try:
        data = post(f"/trainings/stop/{name}")
        session = to_training(data)
        console.print()
        console.print(f"[bold green]Success:[/bold green] Training session [bold white]'{session.name}'[/bold white] has been stopped.")
        console.print()
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command(name="remove")
def remove_training(name: str):
    """
    Remove a training session config/record.
    """
    try:
        data = get(f"/trainings/show/{name}")
        session = to_training(data)
        if typer.confirm(f"Are you sure you want to remove training session '{session.name}'?"):
            delete(f"/trainings/remove/{session.name}")
            console.print(f"[bold green]Success:[/bold green] Training session [bold white]'{session.name}'[/bold white] removed.")
        else:
            console.print("[yellow]Operation aborted.[/yellow]")
    except RemoteAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
