import typer
from conclave.cli.shell import run_shell
from conclave.cli.commands import client, policy, consent, training, audit, organization, user, auth, onboarding, node, monitor, notification, report

app = typer.Typer(
    name="conclave",
    help="Governance Control Plane for Federated Learning",
    no_args_is_help=False,
)

# Register pluggable thin command groups
app.add_typer(client.app, name="client")
app.add_typer(policy.app, name="policy")
app.add_typer(consent.app, name="consent")
app.add_typer(training.app, name="training")
app.add_typer(audit.app, name="audit")
app.add_typer(organization.app, name="organization")
app.add_typer(user.app, name="user")
app.add_typer(auth.app, name="auth")
app.add_typer(onboarding.app, name="onboarding")
app.add_typer(node.app, name="node")
app.add_typer(monitor.app, name="monitor")
app.add_typer(notification.app, name="notification")
app.add_typer(report.app, name="report")

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    Main entry point. If invoked without a subcommand, enter the interactive shell.
    Otherwise, route directly to the standard CLI subcommand.
    """
    if ctx.invoked_subcommand is None:
        run_shell(app)

if __name__ == "__main__":
    app()
