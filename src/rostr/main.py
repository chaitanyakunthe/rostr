import typer

from .people import people_app
from .project import project_app
from .report import report_app
from .config import run_setup_wizard, CONFIG_FILE

app = typer.Typer(help="Rostr: Resource and Project Management CLI", add_completion=False)

# This callback runs before every command
@app.callback(invoke_without_command=True)
def ensure_configured(ctx: typer.Context):
    """
    Ensures the user has run the setup wizard at least once.
    """
    # If config is missing and the user isn't actively trying to run `setup`
    if not CONFIG_FILE.exists() and ctx.invoked_subcommand != "setup":
        run_setup_wizard()

# Add the setup command so users can change settings anytime
@app.command(name="setup")
def setup():
    """Configure Rostr workspace settings (dates, capacities, etc.)"""
    run_setup_wizard()

app.add_typer(people_app, name="people")
app.add_typer(project_app, name="project")
app.add_typer(report_app, name="report")

if __name__ == "__main__":
    app()
