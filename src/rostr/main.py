import typer
import json
from pathlib import Path
from typing import List

# Initialize the Typer app
app = typer.Typer()

# Data Files
PEOPLE = Path("people.json")

def load_people() -> dict:
    try:
        with PEOPLE.open() as f:
            return json.load(f)
    except FileNotFoundError:
        return ["File does not exist"]

def save_people(people:dict):
    with PEOPLE.open("w") as f:
        json.dump(people, f, indent=2)

@app.command()
def add(
    email: str,
    name: str = typer.Option(...,prompt="Enter name", help="The person's full name"),
    capacity: int = typer.Option(40, help="Weekly capacity (max 40 hrs)"),
    skill: List[str] = typer.Option([], help="Add skills as 'name:level' (e.g., --skill ISMS:7)")
):
    # Add a new person to rostr
    people = load_people()

    #Check if email already exists
    if email in people:
        typer.echo(f"Email {email} already exists")
        raise typer.Exit(code=1)

    #Check if email is valid
    if "@" not in email:
        typer.echo(f"Email {email} is not valid")
        raise typer.Exit(code=1)

    people[email] = {
        "name": name,
        "capacity": capacity,
        "skill": skill
    }
    save_people(people)



if __name__ == "__main__":
    app()
