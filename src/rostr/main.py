import typer
import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

# Initialize the Typer app
app = typer.Typer()
console = Console()

# Data Files
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PEOPLE = BASE_DIR / "data" / "people.json"

def load_people() -> dict:
    try:
        with PEOPLE.open() as f:
            return json.load(f)
    except FileNotFoundError:
        # Starting a new file with empty dictionary
        return {}
    except json.JSONDecodeError:
        # Starting a new file with empty dictionary
        return {}

def save_people(people:dict):
    with PEOPLE.open("w") as f:
        json.dump(people, f, indent=2)

@app.command()
def add():
    """Add new people, their capacity and skills."""
    # Load JSON file
    people = load_people()

    email = typer.prompt("Enter email address", type=str)

    #Check if email already exists
    if email in people:
        typer.secho(f" ❌ Error: {email} already exists!", fg="red", bold=True)
        raise typer.Exit(code=1)

    #Check if email is valid
    if "@" not in email:
        typer.echo(f"Email {email} is not valid")
        raise typer.Exit(code=1)

    # Add name and capacity
    name = typer.prompt("Enter name", type=str)
    capacity = typer.prompt("Enter capacity (Weekly available hours)", default=40, type=int)

    # Add skills
    skills = []
    typer.echo("---Skill Entry---")
    while True:
        skill_name = typer.prompt("Skill name (Press '.' to finish)", type=str)
        if skill_name == ".":
            break
        skill_level = typer.prompt(f"Enter {skill_name} level (1-10), 10 being highest skill", type=int)
        skills.append(f"{skill_name}:{skill_level}")

    people[email] = {
        "name": name,
        "capacity": capacity,
        "skill": skills
    }
    save_people(people)
    typer.secho(f"\n✅ Successfully added {name}!", fg="green", bold=True)

@app.command()
def edit():

    """Edit a person's details, including surgical skill updates."""
    people = load_people()
    email = typer.prompt("Enter the email of the person to edit")

    if email not in people:
        typer.secho(f"❌ Error: {email} does not exist", fg="red")
        raise typer.Exit(code=1)

    current_data = people[email]

    # 1. Basic Info Updates
    new_name = typer.prompt("Name", default=current_data["name"])
    new_capacity = typer.prompt("Weekly capacity", default=current_data["capacity"], type=int)

    # 2. Surgical Skill Editing
    skills = current_data.get("skill", [])
    updated_skills = []

    if skills:
        typer.echo("\n--- Reviewing Existing Skills ---")
        for s in skills:
            # Split "Python:5" into name and level
            name, level = s.split(":")

            action = typer.prompt(
                f"Skill '{name}' (Level {level}) -> [K]eep, [U]pdate Level, [D]elete",
                default="K"
            ).upper()

            if action == "K":
                updated_skills.append(s)
            elif action == "U":
                new_level = typer.prompt(f"Enter new level for {name}", type=int)
                updated_skills.append(f"{name}:{new_level}")
            elif action == "D":
                typer.echo(f"Removing {name}...")
                continue # Skip adding to updated_skills

    # 3. Add Brand New Skills
    if typer.confirm("\nAdd any new skills?", default=False):
        typer.echo("Enter new skills (Type '.' for Skill Name to stop)")
        while True:
            s_name = typer.prompt("Skill Name (Type '.' to stop)")
            if s_name == ".":
                break
            s_level = typer.prompt(f"Level for {s_name}", type=int)
            updated_skills.append(f"{s_name}:{s_level}")

    # 4. Save
    people[email] = {
        "name": new_name,
        "capacity": new_capacity,
        "skill": updated_skills
    }

    save_people(people)
    typer.secho(f"\n✅ Updated {new_name} successfully!", fg="green", bold=True)

@app.command()
def delete(email: str):
    """Delete a person from list using email ID"""
    # Delete an existing person in rostr
    people = load_people()

    #Check if email exists
    if email not in people:
        typer.echo(f"Email {email} does not exist")
        raise typer.Exit(code=1)

    del people[email]
    save_people(people)
    typer.secho(f"\n✅ Successfully deleted {email}!", fg="green", bold=True)

@app.command(name="list")
def list_roster(
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="Filter by a specific skill (e.g., Python)"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search in emails, names, and skills")
):
    """Display all people, with optional filtering by skill or general search."""
    people = load_people()

    if not people:
        console.print("[yellow]The list is currently empty.[/yellow]")
        return

    # 1. FILTERING LOGIC
    display_data = {}

    for email, data in people.items():
        include_person = True

        # Check skill filter (case-insensitive, matching just the skill name before the colon)
        if skill:
            has_skill = any(skill.lower() == s.split(":")[0].lower() for s in data.get("skill", []))
            if not has_skill:
                include_person = False

        # Check general search filter (case-insensitive across email, name, and skills)
        if search and include_person:
            search_lower = search.lower()
            in_email = search_lower in email.lower()
            in_name = search_lower in data["name"].lower()
            in_skills = any(search_lower in s.lower() for s in data.get("skill", []))

            if not (in_email or in_name or in_skills):
                include_person = False

        # If the person passed the filters, add them to our display list
        if include_person:
            display_data[email] = data

    # Handle empty results after filtering
    if not display_data:
        console.print("[yellow]No matches found for your search criteria.[/yellow]")
        return

    # 2. DYNAMIC TITLE
    title = "Consultant Overview"
    if skill and search:
        title = f"Search: '{search}' | Skill: '{skill}'"
    elif skill:
        title = f"People with skill: {skill}"
    elif search:
        title = f"Search results for: '{search}'"

    # 3. BUILD THE TABLE
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Email", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Capacity", justify="center", style="green")
    table.add_column("Skills", style="blue")

    for email, data in display_data.items():
        skills_raw = data.get("skill", [])
        formatted_skills = ", ".join([s.replace(":", " (") + ")" for s in skills_raw])

        table.add_row(
            email,
            data["name"],
            f"{data['capacity']} hrs",
            formatted_skills if formatted_skills else "No skills added"
        )

    console.print(table)

if __name__ == "__main__":
    app()
