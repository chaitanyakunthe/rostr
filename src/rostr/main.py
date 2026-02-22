import typer
import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

# 1. Initialize the Main App and Sub-Apps
app = typer.Typer(help="Rostr: Resource and Project Management CLI")
people_app = typer.Typer(help="Manage consultants and their skills")
project_app = typer.Typer(help="Manage projects and resource allocation")

# 2. Attach sub-apps to the main app
app.add_typer(people_app, name="people")
app.add_typer(project_app, name="project")

console = Console()

# 3. Data Files Setup
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PEOPLE = BASE_DIR / "data" / "people.json"
PROJECTS = BASE_DIR / "data" / "projects.json"

# --- HELPER FUNCTIONS ---

def load_people() -> dict:
    try:
        with PEOPLE.open() as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_people(people: dict):
    with PEOPLE.open("w") as f:
        json.dump(people, f, indent=2)

def load_projects() -> dict:
    try:
        with PROJECTS.open() as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_projects(projects: dict):
    with PROJECTS.open("w") as f:
        json.dump(projects, f, indent=2)


# ==========================================
# PEOPLE COMMANDS (Note: @people_app.command)
# ==========================================

@people_app.command(name="add")
def add_person():
    """Add new people, their capacity and skills."""
    people = load_people()
    email = typer.prompt("Enter email address", type=str)

    if email in people:
        typer.secho(f" ❌ Error: {email} already exists!", fg="red", bold=True)
        raise typer.Exit(code=1)

    if "@" not in email:
        typer.echo(f"Email {email} is not valid")
        raise typer.Exit(code=1)

    name = typer.prompt("Enter name", type=str)
    capacity = typer.prompt("Enter capacity (Weekly available hours)", default=40, type=int)

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


@people_app.command(name="edit")
def edit_person():
    """Edit a person's details, including surgical skill updates."""
    people = load_people()
    email = typer.prompt("Enter the email of the person to edit")

    if email not in people:
        typer.secho(f"❌ Error: {email} does not exist", fg="red")
        raise typer.Exit(code=1)

    current_data = people[email]
    new_name = typer.prompt("Name", default=current_data["name"])
    new_capacity = typer.prompt("Weekly capacity", default=current_data["capacity"], type=int)

    skills = current_data.get("skill", [])
    updated_skills = []

    if skills:
        typer.echo("\n--- Reviewing Existing Skills ---")
        for s in skills:
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
                continue

    if typer.confirm("\nAdd any new skills?", default=False):
        typer.echo("Enter new skills (Type '.' for Skill Name to stop)")
        while True:
            s_name = typer.prompt("Skill Name (Type '.' to stop)")
            if s_name == ".":
                break
            s_level = typer.prompt(f"Level for {s_name}", type=int)
            updated_skills.append(f"{s_name}:{s_level}")

    people[email] = {
        "name": new_name,
        "capacity": new_capacity,
        "skill": updated_skills
    }
    save_people(people)
    typer.secho(f"\n✅ Updated {new_name} successfully!", fg="green", bold=True)


@people_app.command(name="delete")
def delete_person(email: str):
    """Delete a person from list using email ID"""
    people = load_people()
    if email not in people:
        typer.echo(f"Email {email} does not exist")
        raise typer.Exit(code=1)

    del people[email]
    save_people(people)
    typer.secho(f"\n✅ Successfully deleted {email}!", fg="green", bold=True)


@people_app.command(name="list")
def list_roster(
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="Filter by a specific skill (e.g., Python)"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search in emails, names, and skills")
):
    """Display all people, with optional filtering by skill or general search."""
    people = load_people()
    if not people:
        console.print("[yellow]The list is currently empty.[/yellow]")
        return

    display_data = {}
    for email, data in people.items():
        include_person = True
        if skill:
            has_skill = any(skill.lower() == s.split(":")[0].lower() for s in data.get("skill", []))
            if not has_skill: include_person = False
        if search and include_person:
            search_lower = search.lower()
            in_email = search_lower in email.lower()
            in_name = search_lower in data["name"].lower()
            in_skills = any(search_lower in s.lower() for s in data.get("skill", []))
            if not (in_email or in_name or in_skills): include_person = False
        if include_person: display_data[email] = data

    if not display_data:
        console.print("[yellow]No matches found for your search criteria.[/yellow]")
        return

    title = "Consultant Overview"
    if skill and search: title = f"Search: '{search}' | Skill: '{skill}'"
    elif skill: title = f"People with skill: {skill}"
    elif search: title = f"Search results for: '{search}'"

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Email", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Capacity", justify="center", style="green")
    table.add_column("Skills", style="blue")

    for email, data in display_data.items():
        skills_raw = data.get("skill", [])
        formatted_skills = ", ".join([s.replace(":", " (") + ")" for s in skills_raw])
        table.add_row(email, data["name"], f"{data['capacity']} hrs", formatted_skills if formatted_skills else "No skills added")

    console.print(table)


# ==========================================
# PROJECT COMMANDS (Note: @project_app.command)
# ==========================================

@project_app.command(name="add")
def add_project():
    """Add a new project with required skills using a guided wizard."""
    projects = load_projects()

    project_id = typer.prompt("Enter a unique Project ID (e.g., alpha-audit)")
    if project_id in projects:
        typer.secho(f"❌ Error: Project '{project_id}' already exists!", fg="red", bold=True)
        raise typer.Exit(code=1)

    name = typer.prompt("Project Name")
    desc = typer.prompt("Brief Description")
    hours_input = typer.prompt("Total hours needed (Enter a number, or 'T&M' / 'TBD')", default="TBD")

    # If they typed a number (like "120"), save it as an integer.
    # Otherwise, save the text (like "T&M").
    if hours_input.isdigit():
        hours = int(hours_input)
    else:
        hours = hours_input.strip().upper()

    required_skills = []
    typer.echo("\n--- Required Skills ---")
    while True:
        s_name = typer.prompt("Required Skill Name (Type '.' to stop)")
        if s_name == ".":
            break
        s_level = typer.prompt(f"Minimum Level for {s_name}", type=int)
        required_skills.append(f"{s_name}:{s_level}")

    projects[project_id] = {
        "name": name,
        "description": desc,
        "total_hours_needed": hours,
        "required_skills": required_skills,
        "allocated_people": []
    }

    save_projects(projects)
    typer.secho(f"\n✅ Successfully created project: {name}!", fg="green", bold=True)

@project_app.command(name="edit")
def edit_project():
    """Edit a project's details and required skills."""
    projects = load_projects()
    project_id = typer.prompt("Enter the Project ID to edit")

    if project_id not in projects:
        typer.secho(f"❌ Error: Project '{project_id}' does not exist", fg="red")
        raise typer.Exit(code=1)

    current_data = projects[project_id]

    # 1. Basic Info Updates
    new_name = typer.prompt("Project Name", default=current_data["name"])
    new_desc = typer.prompt("Brief Description", default=current_data["description"])

    # Handle hours (Int or String like T&M)
    current_hours = str(current_data.get("total_hours_needed", "TBD"))
    hours_input = typer.prompt("Total hours needed (Enter a number, or 'T&M' / 'TBD')", default=current_hours)

    if hours_input.isdigit():
        new_hours = int(hours_input)
    else:
        new_hours = hours_input.strip().upper()

    # 2. Surgical Skill Editing
    skills = current_data.get("required_skills", [])
    updated_skills = []

    if skills:
        typer.echo("\n--- Reviewing Required Skills ---")
        for s in skills:
            name, level = s.split(":")
            action = typer.prompt(
                f"Required Skill '{name}' (Level {level}) -> [K]eep, [U]pdate Level, [D]elete",
                default="K"
            ).upper()

            if action == "K":
                updated_skills.append(s)
            elif action == "U":
                new_level = typer.prompt(f"Enter new minimum level for {name}", type=int)
                updated_skills.append(f"{name}:{new_level}")
            elif action == "D":
                typer.echo(f"Removing {name}...")
                continue

    # 3. Add Brand New Skills
    if typer.confirm("\nAdd any new required skills?", default=False):
        typer.echo("Enter new skills (Type '.' for Skill Name to stop)")
        while True:
            s_name = typer.prompt("Required Skill Name (Type '.' to stop)")
            if s_name == ".":
                break
            s_level = typer.prompt(f"Minimum Level for {s_name}", type=int)
            updated_skills.append(f"{s_name}:{s_level}")

    # 4. Save while preserving allocations!
    projects[project_id] = {
        "name": new_name,
        "description": new_desc,
        "total_hours_needed": new_hours,
        "required_skills": updated_skills,
        "allocated_people": current_data.get("allocated_people", []) # Crucial step!
    }

    save_projects(projects)
    typer.secho(f"\n✅ Updated project '{project_id}' successfully!", fg="green", bold=True)

@project_app.command(name="delete")
def delete_project(project_id: str):
    """Delete a project using its Project ID."""
    projects = load_projects()

    if project_id not in projects:
        typer.secho(f"❌ Error: Project '{project_id}' does not exist", fg="red")
        raise typer.Exit(code=1)

    # Smart Check: Are people already working on this?
    allocated = projects[project_id].get("allocated_people", [])
    if allocated:
        typer.secho(f"⚠️ Warning: There are {len(allocated)} people currently allocated to this project!", fg="yellow")
        if not typer.confirm("Are you sure you want to delete it anyway?"):
            typer.echo("Deletion cancelled.")
            raise typer.Exit()

    del projects[project_id]
    save_projects(projects)
    typer.secho(f"\n✅ Successfully deleted project '{project_id}'!", fg="green", bold=True)

@project_app.command(name="list")
def list_projects(
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="Filter by a required skill (e.g., Python)"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search in project IDs, names, and descriptions")
    ):
    """Display all projects, with optional filtering by required skill or general search."""
    projects = load_projects()
    if not projects:
        console.print("[yellow]The project list is currently empty.[/yellow]")
        return

    # 1. FILTERING LOGIC
    display_data = {}
    for proj_id, data in projects.items():
        include_proj = True

        if skill:
            has_skill = any(skill.lower() == s.split(":")[0].lower() for s in data.get("required_skills", []))
            if not has_skill:
                include_proj = False

        if search and include_proj:
            search_lower = search.lower()
            in_id = search_lower in proj_id.lower()
            in_name = search_lower in data["name"].lower()
            in_desc = search_lower in data["description"].lower()

            if not (in_id or in_name or in_desc):
                include_proj = False

        if include_proj:
            display_data[proj_id] = data

    if not display_data:
        console.print("[yellow]No projects found matching your search criteria.[/yellow]")
        return

    # 2. DYNAMIC TITLE
    title = "Projects Overview"
    if skill and search: title = f"Search: '{search}' | Required Skill: '{skill}'"
    elif skill: title = f"Projects requiring skill: {skill}"
    elif search: title = f"Search results for: '{search}'"

    # 3. BUILD THE TABLE
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Project ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Description", style="dim", max_width=30)
    table.add_column("Hours", justify="center", style="green")
    table.add_column("Required Skills", style="blue")
    table.add_column("Allocated", justify="center", style="yellow")

    for proj_id, data in display_data.items():
        # Format the required skills exactly like we did for people
        skills_raw = data.get("required_skills", [])
        formatted_skills = ", ".join([s.replace(":", " (") + ")" for s in skills_raw])

        # Check how many people are currently allocated to this project
        allocated_count = len(data.get("allocated_people", []))
        alloc_str = f"{allocated_count} people" if allocated_count > 0 else "None"

        # Determine how to display the hours
        raw_hours = data.get("total_hours_needed", "TBD")
        if isinstance(raw_hours, int) or (isinstance(raw_hours, str) and raw_hours.isdigit()):
            hours_display = f"{raw_hours} hrs"
        else:
            hours_display = str(raw_hours) # Prints "T&M", "TBD", etc.

        table.add_row(
            proj_id,
            data["name"],
            data["description"],
            hours_display, # Use our new smart display variable
            formatted_skills if formatted_skills else "No specific skills",
            alloc_str
        )

    console.print(table)

if __name__ == "__main__":
    app()
