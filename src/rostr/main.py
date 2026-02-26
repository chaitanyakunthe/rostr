import typer

# Import sub-apps from our newly created modules
from .people import people_app
from .project import project_app
from .report import report_app

# Initialize the Main App
app = typer.Typer(help="Rostr: Resource and Project Management CLI", add_completion=False)

# Register the sub-apps
app.add_typer(people_app, name="people")
app.add_typer(project_app, name="project")
app.add_typer(report_app, name="report")

if __name__ == "__main__":
    app()
