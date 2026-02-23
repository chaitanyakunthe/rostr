import re
import uuid
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# Relative import for our local ledger module
from .ledger import append_event, load_state, PEOPLE_FILE, PROJECTS_FILE, ALLOCATIONS_FILE

# Initialize the Main App and Sub-Apps
app = typer.Typer(help="Rostr: Resource and Project Management CLI")
people_app = typer.Typer(help="Manage consultants and their skills")
project_app = typer.Typer(help="Manage projects and resource allocation")
report_app = typer.Typer(help="Generate utilization and allocation reports")

app.add_typer(people_app, name="people")
app.add_typer(project_app, name="project")
app.add_typer(report_app, name="report")

console = Console()

# 3. Data Files Setup
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PEOPLE = BASE_DIR / "data" / "people.json"
PROJECTS = BASE_DIR / "data" / "projects.json"

# --- HELPER FUNCTIONS ---

def generate_project_id(name: str, existing_projects: dict) -> str:
    """Converts a Project Name into a clean, unique ID (e.g., 'My Project' -> 'my-project')."""
    # Lowercase, replace spaces with hyphens, remove special characters
    base_id = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not base_id:
        base_id = "project"

    project_id = base_id
    counter = 1

    # If the ID exists (even if deleted), append a number to keep it unique
    while project_id in existing_projects:
        counter += 1
        project_id = f"{base_id}-{counter}"

    return project_id

def prompt_for_date(prompt_text: str, allow_empty: bool = False) -> str:
    """Forces valid YYYY-MM-DD date, with an option to skip if allow_empty is True."""
    prompt_str = f"{prompt_text} (YYYY-MM-DD)"
    if allow_empty:
        prompt_str += typer.style(" [Press Enter to skip]", fg=typer.colors.CYAN)

    while True:
        date_str = typer.prompt(prompt_str, default="", show_default=False).strip()

        if allow_empty and not date_str:
            return "" # Return empty string if they skipped

        try:
            valid_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            return valid_date.isoformat()
        except ValueError:
            typer.secho("⚠️ Invalid format. Please use YYYY-MM-DD (e.g., 2024-10-31).", fg="yellow")

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
    # Instantly load the compiled state to check for duplicates
    people = load_state(PEOPLE_FILE)
    email = typer.prompt("Enter email address", type=str)

    # Check if they exist AND are currently active
    if email in people and people[email].get("is_active", True):
        typer.secho(f" ❌ Error: {email} already exists and is active!", fg="red", bold=True)
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
        skill_level = typer.prompt(f"Enter {skill_name} level (1-10)", type=int)
        skills.append(f"{skill_name}:{skill_level}")

    # 1. Create the Payload
    payload = {
        "email": email,
        "name": name,
        "capacity": capacity,
        "skill": skills,
        "is_active": True # Explicitly set them as active when adding
    }

    # 2. Fire the Event! (The ledger handles saving and rebuilding the JSON)
    append_event("PERSON_ADDED", payload)

    typer.secho(f"\n✅ Successfully added {name} to the ledger!", fg="green", bold=True)


@people_app.command(name="list")
def list_roster(
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="Filter by a specific skill"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search in emails, names, and skills")
    ):
    """Display all active people, with optional filtering."""
    people = load_state(PEOPLE_FILE)

    if not people:
        console.print("[yellow]The roster is currently empty.[/yellow]")
        return

    display_data = {}
    for email, data in people.items():
        # NEW: Skip people who have been deleted/deactivated!
        if not data.get("is_active", True):
            continue

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
        console.print("[yellow]No active matches found for your search criteria.[/yellow]")
        return

    title = "Active Consultant Overview"
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

@people_app.command(name="edit")
def edit_person():
    """Edit a person's details, including surgical skill updates."""
    # Instantly load the compiled state
    people = load_state(PEOPLE_FILE)
    email = typer.prompt("Enter the email of the person to edit")

    # Check if they exist AND are active
    if email not in people or not people[email].get("is_active", True):
        typer.secho(f"❌ Error: {email} does not exist or is inactive.", fg="red")
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
            name, level = s.split(":")

            # Using the UI styling trick we added earlier!
            styled_default = typer.style("[K]", fg=typer.colors.CYAN, bold=True)
            prompt_text = f"Skill '{name}' (Level {level}) -> [K]eep, [U]pdate Level, [D]elete {styled_default}"

            action = typer.prompt(
                prompt_text,
                default="K",
                show_default=False
            ).upper()

            if action == "K":
                updated_skills.append(s)
            elif action == "U":
                new_level = typer.prompt(f"Enter new level for {name}", type=int)
                updated_skills.append(f"{name}:{new_level}")
            elif action == "D":
                typer.echo(f"Removing {name}...")
                continue

    # 3. Add Brand New Skills
    if typer.confirm("\nAdd any new skills?", default=False):
        typer.echo("Enter new skills (Type '.' for Skill Name to stop)")
        while True:
            s_name = typer.prompt("Skill Name (Type '.' to stop)")
            if s_name == ".":
                break
            s_level = typer.prompt(f"Level for {s_name}", type=int)
            updated_skills.append(f"{s_name}:{s_level}")

    # 4. Create the Payload
    payload = {
        "email": email,
        "name": new_name,
        "capacity": new_capacity,
        "skill": updated_skills
    }

    # 5. Fire the Event!
    append_event("PERSON_EDITED", payload)

    typer.secho(f"\n✅ Successfully updated {new_name} in the ledger!", fg="green", bold=True)

@people_app.command(name="timeoff")
def add_timeoff(email: Optional[str] = typer.Argument(None)):
    """Log planned unavailability (PTO, vacation, etc.) for a consultant."""
    people = load_state(PEOPLE_FILE)

    if not email:
        email = typer.prompt("Enter the consultant's email")

    if email not in people or not people[email].get("is_active", True):
        typer.secho(f"❌ Error: {email} does not exist or is inactive.", fg="red")
        raise typer.Exit(code=1)

    typer.echo(f"\n--- Logging Time Off for {people[email]['name']} ---")
    start_date = prompt_for_date("Start Date of Leave", allow_empty=False)
    end_date = prompt_for_date("End Date of Leave", allow_empty=False)

    if end_date < start_date:
        typer.secho("❌ Error: End date cannot be before the start date!", fg="red", bold=True)
        raise typer.Exit(code=1)

    reason = typer.prompt("Reason (e.g., Vacation, Sick Leave)", default="PTO")

    payload = {
        "email": email,
        "start_date": start_date,
        "end_date": end_date,
        "reason": reason
    }

    append_event("UNAVAILABILITY_ADDED", payload)
    typer.secho(f"\n✅ Logged {reason} for {people[email]['name']} from {start_date} to {end_date}.", fg="green", bold=True)

@people_app.command(name="offboard")
def offboard_person(email: Optional[str] = typer.Argument(None)):
    """Set a Last Working Day (exit date) for a consultant."""
    people = load_state(PEOPLE_FILE)

    if not email:
        email = typer.prompt("Enter the consultant's email")

    if email not in people or not people[email].get("is_active", True):
        typer.secho(f"❌ Error: {email} does not exist or is inactive.", fg="red")
        raise typer.Exit(code=1)

    typer.echo(f"\n--- Setting Last Working Day for {people[email]['name']} ---")
    exit_date = prompt_for_date("Last Working Day", allow_empty=False)

    payload = {
        "email": email,
        "exit_date": exit_date
    }

    append_event("PERSON_OFFBOARDED", payload)
    typer.secho(f"\n✅ Marked {exit_date} as the Last Working Day for {people[email]['name']}.", fg="green", bold=True)

@people_app.command(name="delete")
def delete_person(email: str):
    """Deactivate a person from the active roster."""
    people = load_state(PEOPLE_FILE)

    if email not in people or not people[email].get("is_active", True):
        typer.echo(f"Email {email} does not exist or is already inactive.")
        raise typer.Exit(code=1)

    # Confirm before deactivating
    person_name = people[email]['name']
    if not typer.confirm(f"Are you sure you want to remove {person_name} from the active roster?"):
        typer.echo("Deletion cancelled.")
        raise typer.Exit()

    # Create the Payload - We only need the email for the reducer to know who to deactivate
    payload = {
        "email": email
    }

    # Fire the Event!
    append_event("PERSON_DELETED", payload)

    typer.secho(f"\n✅ Successfully deactivated {person_name}!", fg="green", bold=True)

# ==========================================
# PROJECT COMMANDS
# ==========================================

@project_app.command(name="add")
def add_project():
    """Add a new project with required skills, status, and probability."""
    projects = load_state(PROJECTS_FILE)

    name = typer.prompt("Project Name")

    # Auto-generate the ID
    project_id = generate_project_id(name, projects)
    typer.secho(f"🤖 Auto-assigned Project ID: {project_id}\n", fg="cyan")

    # ... then continue asking for description, status, etc.
    if project_id in projects and projects[project_id].get("status") != "Deleted":
        typer.secho(f"❌ Error: Project '{project_id}' already exists!", fg="red", bold=True)
        raise typer.Exit(code=1)

    desc = typer.prompt("Brief Description")

    # NEW: Pipeline forecasting data
    status = typer.prompt(
        "Status [Proposed/Active/Completed/Lost]",
        default="Proposed"
    ).capitalize()

    probability = typer.prompt("Win Probability (0-100%)", type=int, default=100)

    # Handle hours (Int or String like T&M)
    hours_input = typer.prompt("Total hours needed (Enter a number, or 'T&M' / 'TBD')", default="TBD")
    new_hours = int(hours_input) if hours_input.isdigit() else hours_input.strip().upper()

    required_skills = []
    typer.echo("\n--- Required Skills ---")
    while True:
        s_name = typer.prompt("Required Skill Name (Type '.' for Skill Name to stop)")
        if s_name == ".":
            break
        s_level = typer.prompt(f"Minimum Level for {s_name}", type=int)
        required_skills.append(f"{s_name}:{s_level}")

    # 1. Create the Payload
    payload = {
        "project_id": project_id,
        "name": name,
        "description": desc,
        "status": status,
        "probability": probability,
        "total_hours_needed": new_hours,
        "required_skills": required_skills
    }

    # 2. Fire the Event!
    append_event("PROJECT_ADDED", payload)
    typer.secho(f"\n✅ Successfully created project: {name} in the ledger!", fg="green", bold=True)

@project_app.command(name="list")
def list_projects(
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="Filter by a required skill"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search in IDs, names, and descriptions")
    ):
    """Display all active projects."""
    projects = load_state(PROJECTS_FILE)

    if not projects:
        console.print("[yellow]The project list is currently empty.[/yellow]")
        return

    display_data = {}
    for proj_id, data in projects.items():
        # Hide deleted projects!
        if data.get("status") == "Deleted":
            continue

        include_proj = True

        if skill:
            has_skill = any(skill.lower() == s.split(":")[0].lower() for s in data.get("required_skills", []))
            if not has_skill: include_proj = False

        if search and include_proj:
            search_lower = search.lower()
            in_id = search_lower in proj_id.lower()
            in_name = search_lower in data["name"].lower()
            in_desc = search_lower in data["description"].lower()
            if not (in_id or in_name or in_desc): include_proj = False

        if include_proj:
            display_data[proj_id] = data

    if not display_data:
        console.print("[yellow]No projects found matching your search criteria.[/yellow]")
        return

    title = "Projects Overview"
    if skill and search: title = f"Search: '{search}' | Required Skill: '{skill}'"
    elif skill: title = f"Projects requiring skill: {skill}"
    elif search: title = f"Search results for: '{search}'"

    # BUILD THE TABLE (Now with Status and Probability!)
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Project ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Prob.", justify="right", style="green")
    table.add_column("Hours", justify="center", style="magenta")
    table.add_column("Required Skills", style="blue")

    for proj_id, data in display_data.items():
        skills_raw = data.get("required_skills", [])
        formatted_skills = ", ".join([s.replace(":", " (") + ")" for s in skills_raw])

        raw_hours = data.get("total_hours_needed", "TBD")
        hours_display = f"{raw_hours}h" if isinstance(raw_hours, int) or (isinstance(raw_hours, str) and raw_hours.isdigit()) else str(raw_hours)

        table.add_row(
            proj_id,
            data["name"],
            data.get("status", "Unknown"),
            f"{data.get('probability', 100)}%",
            hours_display,
            formatted_skills if formatted_skills else "No specific skills"
        )

    console.print(table)


@project_app.command(name="edit")
def edit_project():
    """Edit a project's details, pipeline status, and required skills."""
    # ---- LISTING PROJECTS ---
    projects = load_state(PROJECTS_FILE)
    typer.secho("\n--- Active Projects ---", fg="cyan", bold=True)
    for p_id, p_data in projects.items():
        if p_data.get("status") != "Deleted":
            typer.echo(f"• {p_id} ({p_data['name']})")
    typer.echo("-----------------------\n")
    # --- LISTING ENDS ---

    project_id = typer.prompt("Enter the Project ID to edit")

    if project_id not in projects or projects[project_id].get("status") == "Deleted":
        typer.secho(f"❌ Error: Project '{project_id}' does not exist.", fg="red")
        raise typer.Exit(code=1)

    current_data = projects[project_id]

    new_name = typer.prompt("Project Name", default=current_data["name"])
    new_desc = typer.prompt("Brief Description", default=current_data.get("description", ""))
    new_status = typer.prompt("Status [Proposed/Active/Completed/Lost]", default=current_data.get("status", "Proposed")).capitalize()
    new_prob = typer.prompt("Win Probability (0-100%)", type=int, default=current_data.get("probability", 100))

    current_hours = str(current_data.get("total_hours_needed", "TBD"))
    hours_input = typer.prompt("Total hours needed", default=current_hours)
    new_hours = int(hours_input) if hours_input.isdigit() else hours_input.strip().upper()

    skills = current_data.get("required_skills", [])
    updated_skills = []

    if skills:
        typer.echo("\n--- Reviewing Required Skills ---")
        for s in skills:
            name, level = s.split(":")
            styled_default = typer.style("[K]", fg=typer.colors.CYAN, bold=True)
            action = typer.prompt(f"Required Skill '{name}' (Level {level}) -> [K]eep, [U]pdate Level, [D]elete {styled_default}", default="K", show_default=False).upper()

            if action == "K":
                updated_skills.append(s)
            elif action == "U":
                new_level = typer.prompt(f"Enter new minimum level for {name}", type=int)
                updated_skills.append(f"{name}:{new_level}")
            elif action == "D":
                typer.echo(f"Removing {name}...")
                continue

    if typer.confirm("\nAdd any new required skills?", default=False):
        while True:
            s_name = typer.prompt("Required Skill Name (Type '.' to stop)")
            if s_name == ".": break
            s_level = typer.prompt(f"Minimum Level for {s_name}", type=int)
            updated_skills.append(f"{s_name}:{s_level}")

    payload = {
        "project_id": project_id,
        "name": new_name,
        "description": new_desc,
        "status": new_status,
        "probability": new_prob,
        "total_hours_needed": new_hours,
        "required_skills": updated_skills
    }

    append_event("PROJECT_EDITED", payload)
    typer.secho(f"\n✅ Updated project '{project_id}' successfully!", fg="green", bold=True)


@project_app.command(name="delete")
def delete_project(project_id: Optional[str] = typer.Argument(None)):
    """Soft delete a project."""
    projects = load_state(PROJECTS_FILE)

    # If they didn't provide an ID in the command line, show the cheat sheet and ask!
    if not project_id:
        typer.secho("\n--- Active Projects ---", fg="cyan", bold=True)
        active_found = False

        for p_id, p_data in projects.items():
            if p_data.get("status") != "Deleted":
                typer.echo(f"• {p_id} ({p_data['name']})")
                active_found = True

        if not active_found:
            typer.secho("No active projects found to delete.", fg="yellow")
            raise typer.Exit()

        typer.echo("-----------------------\n")
        project_id = typer.prompt("Enter the Project ID to delete")

    # Now proceed with the normal validation
    if project_id not in projects or projects[project_id].get("status") == "Deleted":
        typer.secho(f"❌ Error: Project '{project_id}' does not exist.", fg="red")
        raise typer.Exit(code=1)

    if not typer.confirm(f"Are you sure you want to delete '{projects[project_id]['name']}'?"):
        typer.echo("Deletion cancelled.")
        raise typer.Exit()

    # Fire the event
    payload = {"project_id": project_id}
    append_event("PROJECT_DELETED", payload)
    typer.secho(f"\n✅ Successfully marked project '{project_id}' as deleted!", fg="green", bold=True)

@project_app.command(name="allocate")
def allocate_person(project_id: Optional[str] = typer.Argument(None)):
    """Allocate a consultant to a project with flexible skill matching and dates."""
    projects = load_state(PROJECTS_FILE)
    people = load_state(PEOPLE_FILE)

    if not projects or not people:
        typer.secho("⚠️ Ensure you have both active people and projects first!", fg="yellow")
        raise typer.Exit()

    # --- 1. SELECT PROJECT ---
    if not project_id:
        typer.secho("\n--- Active Projects ---", fg="cyan", bold=True)
        for p_id, p_data in projects.items():
            if p_data.get("status") != "Deleted":
                typer.echo(f"• {p_id} ({p_data['name']})")
        typer.echo("-----------------------\n")
        project_id = typer.prompt("Enter the Project ID to staff")

    if project_id not in projects or projects[project_id].get("status") == "Deleted":
        typer.secho(f"❌ Error: Project '{project_id}' does not exist.", fg="red", bold=True)
        raise typer.Exit(code=1)

    project = projects[project_id]
    req_skills_raw = project.get("required_skills", [])

    # Helper function to check if a person meets ALL required skills for this project
    def is_match(person_skills: list, required_skills: list) -> bool:
        if not required_skills: return True

        # Convert lists like ["Python:5"] into dictionaries like {"python": 5}
        p_dict = {s.split(":")[0].lower(): int(s.split(":")[1]) for s in person_skills}
        r_dict = {s.split(":")[0].lower(): int(s.split(":")[1]) for s in required_skills}

        for r_name, r_level in r_dict.items():
            if r_name not in p_dict or p_dict[r_name] < r_level:
                return False
        return True

    # --- 2. SELECT PERSON ---
    typer.echo(f"\n--- Staffing: {project['name']} ---")
    if req_skills_raw:
        typer.secho(f"Project needs: {', '.join(req_skills_raw)}\n", fg="cyan")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Match", justify="center")
    table.add_column("Email", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Base Cap.", style="green")
    table.add_column("Skills", style="blue")

    # Sort people so exact matches appear at the top of the table
    sorted_people = sorted(
        people.items(),
        key=lambda item: is_match(item[1].get("skill", []), req_skills_raw),
        reverse=True
    )

    for email, data in sorted_people:
        if not data.get("is_active", True):
            continue

        person_skills = data.get("skill", [])
        formatted_skills = ", ".join([s.replace(":", " (") + ")" for s in person_skills])

        # Add visual indicator for perfect matches
        match_icon = "✅" if is_match(person_skills, req_skills_raw) else "❌"

        table.add_row(
            match_icon,
            email,
            data['name'],
            f"{data['capacity']}h",
            formatted_skills if formatted_skills else "None"
        )

    console.print(table)

    email = typer.prompt("\nEnter the Email of the person to allocate")
    if email not in people or not people[email].get("is_active", True):
        typer.secho("❌ Error: Email not found or inactive.", fg="red")
        raise typer.Exit(code=1)

    person_name = people[email]["name"]

    # If they picked someone with an ❌, double check with them
    if not is_match(people[email].get("skill", []), req_skills_raw):
        typer.secho(f"\n⚠️ {person_name} does not meet all the minimum skill requirements for this project.", fg="yellow")
        if not typer.confirm("Do you want to allocate them anyway?", default=True):
            raise typer.Exit()

    # --- 3. COLLECT ALLOCATION DATA ---
    hours = typer.prompt(f"\nHow many hours per week will {person_name} work on this?", type=int)

    typer.echo("\n--- Allocation Timeline ---")
    start_date = prompt_for_date("Start Date", allow_empty=False) # Start date is mandatory
    end_date = prompt_for_date("End Date", allow_empty=True)      # End date is optional

    # Default to 1 year if left blank
    if not end_date:
        start_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = (start_obj + timedelta(days=365)).strftime("%Y-%m-%d")
        typer.secho(f"🤖 No end date provided. Defaulting to 1 year: {end_date}", fg="cyan", italic=True)

    if end_date < start_date:
        typer.secho("❌ Error: End date cannot be before the start date!", fg="red", bold=True)
        raise typer.Exit(code=1)

    # --- 4. FIRE THE EVENT ---
    allocation_id = uuid.uuid4().hex[:8]

    payload = {
        "allocation_id": allocation_id,
        "project_id": project_id,
        "email": email,
        "hours": hours,
        "start_date": start_date,
        "end_date": end_date
    }

    append_event("ALLOCATION_ADDED", payload)
    typer.secho(f"\n✅ Successfully allocated {person_name} to '{project['name']}' from {start_date} to {end_date}!", fg="green", bold=True)

# ==========================================
# REPORT COMMANDS
# ==========================================

# --- Report Helpers ---
def get_utilization_color(utilization_pct: float) -> str:
    """Helper to color-code utilization: Red (Over 100%), Green (75-100%), Yellow (Under 75%)."""
    if utilization_pct > 100: return "red"
    if utilization_pct >= 75: return "green"
    return "yellow"

def calculate_utilization_at_date(email: str, target_date: str, people: dict, projects: dict, allocations: dict) -> float:
    """Calculates the expected utilization % for a specific person on a specific date."""
    person_data = people.get(email, {})
    base_capacity = person_data.get("capacity", 40)
    if base_capacity == 0: return 0.0

    expected_hours = 0.0

    for alloc_id, alloc_data in allocations.items():
        if alloc_data["email"] == email:
            start = alloc_data["start_date"]
            end = alloc_data.get("end_date", "2099-12-31")

            # If the date falls in the allocation window
            if start <= target_date <= end:
                proj_id = alloc_data["project_id"]
                project = projects.get(proj_id, {})
                proj_status = project.get("status", "Unknown")

                if proj_status not in ["Deleted", "Lost", "Completed"]:
                    # Apply probability
                    probability = project.get("probability", 100)
                    weighted_hours = alloc_data["hours"] * (probability / 100.0)
                    expected_hours += weighted_hours

    return (expected_hours / base_capacity) * 100

# ---- Helpers End ----
@report_app.command(name="current")
def report_current():
    """Report: Current utilization based on today's active allocations."""
    people = load_state(PEOPLE_FILE)
    projects = load_state(PROJECTS_FILE)
    allocations = load_state(ALLOCATIONS_FILE)

    today = datetime.now().date().isoformat()

    table = Table(title=f"Current Utilization (As of {today})", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Capacity", justify="right")
    table.add_column("Allocated", justify="right")
    table.add_column("Total Util.", justify="right")
    table.add_column("Project Breakdown", style="white") # Renamed and styled for better readability

    for email, person_data in people.items():
        if not person_data.get("is_active", True): continue

        base_capacity = person_data.get("capacity", 40)
        if base_capacity == 0: continue

        total_allocated_hours = 0
        project_breakdown_lines = []

        # Find all allocations for this person happening TODAY
        for alloc_id, alloc_data in allocations.items():
            if alloc_data["email"] == email:
                start = alloc_data["start_date"]
                end = alloc_data.get("end_date", "2099-12-31")

                if start <= today <= end:
                    proj_id = alloc_data["project_id"]
                    proj_status = projects.get(proj_id, {}).get("status", "Unknown")

                    if proj_status not in ["Deleted", "Lost", "Completed"]:
                        hours = alloc_data["hours"]
                        total_allocated_hours += hours

                        proj_name = projects[proj_id]["name"]
                        proj_util_pct = (hours / base_capacity) * 100

                        # Add a formatted line specifically for this project
                        project_breakdown_lines.append(f"• {proj_name}: {hours}h ([dim]{proj_util_pct:.0f}%[/dim])")

        utilization_pct = (total_allocated_hours / base_capacity) * 100
        color = get_utilization_color(utilization_pct)

        # Join the breakdown lines with a newline character, or show "Bench"
        breakdown_text = "\n".join(project_breakdown_lines) if project_breakdown_lines else "[dim italic]Bench / Available[/dim italic]"

        table.add_row(
            person_data["name"],
            f"{base_capacity}h",
            f"{total_allocated_hours}h",
            f"[{color}]{utilization_pct:.0f}%[/{color}]",
            breakdown_text
        )

        # Optional: Add a subtle divider between rows if they are multi-line for cleaner reading
        table.add_section()

    console.print(table)

@report_app.command(name="forecast")
def report_forecast(
    months: int = typer.Option(3, "--months", "-m", help="Number of months to forecast into the future"),
    view: str = typer.Option("all", "--view", "-v", help="Filter projects: 'all', 'active' (certain), or 'probable' (pipeline)")
    ):
    """Report: Multi-month predicted utilization with project breakdown and context-aware filtering."""
    people = load_state(PEOPLE_FILE)
    projects = load_state(PROJECTS_FILE)
    allocations = load_state(ALLOCATIONS_FILE)

    view = view.lower()
    if view not in ["all", "active", "probable"]:
        typer.secho("❌ Error: View must be 'all', 'active', or 'probable'.", fg="red")
        raise typer.Exit(code=1)

    time_buckets = []
    current_date = datetime.now().date()
    curr_year = current_date.year
    curr_month = current_date.month

    for _ in range(months):
        curr_month += 1
        if curr_month > 12:
            curr_month = 1
            curr_year += 1

        target_date = datetime(curr_year, curr_month, 15).date()
        label = target_date.strftime("%b %Y")
        time_buckets.append({"label": label, "date": target_date.isoformat()})

    title_suffix = ""
    if view == "active": title_suffix = " [ACTIVE/CERTAIN ONLY]"
    elif view == "probable": title_suffix = " [PIPELINE/PROBABLE ONLY]"

    table = Table(
        title=f"Pipeline Forecast ({months} Months){title_suffix}",
        show_header=True,
        header_style="bold magenta"
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Cap.", justify="right", style="dim")

    for bucket in time_buckets:
        table.add_column(bucket["label"])

    for email, person_data in people.items():
        if not person_data.get("is_active", True): continue

        base_capacity = person_data.get("capacity", 40)
        if base_capacity == 0: continue

        row_data = [person_data["name"], f"{base_capacity}h"]

        for bucket in time_buckets:
            target_str = bucket["date"]

            # Track both types of hours simultaneously
            active_hours = 0.0
            probable_hours = 0.0
            breakdown_lines = []

            for alloc_id, alloc_data in allocations.items():
                if alloc_data["email"] == email:
                    start = alloc_data["start_date"]
                    end = alloc_data.get("end_date", "2099-12-31")

                    if start <= target_str <= end:
                        proj_id = alloc_data["project_id"]
                        project = projects.get(proj_id, {})
                        status = project.get("status", "Unknown").lower()

                        if status not in ["deleted", "lost", "completed"]:
                            prob = project.get("probability", 100)
                            is_probable = (status == "proposed" or prob < 100)

                            weighted_hrs = alloc_data["hours"] * (prob / 100.0)
                            p_name = project.get("name", proj_id)

                            # Sort the hours into their respective buckets
                            if is_probable:
                                probable_hours += weighted_hrs
                                if view in ["all", "probable"]:
                                    breakdown_lines.append(f"[cyan]• {p_name}: {weighted_hrs:.1f}h ([italic]{prob}% prob[/italic])[/cyan]")
                            else:
                                active_hours += weighted_hrs
                                if view in ["all", "active"]:
                                    breakdown_lines.append(f"• {p_name}: {weighted_hrs:.1f}h")

            # Determine which hours to use for the main calculation based on the view
            if view == "all":
                expected_hours = active_hours + probable_hours
            elif view == "active":
                expected_hours = active_hours
            else: # view == "probable"
                expected_hours = probable_hours

            util_pct = (expected_hours / base_capacity) * 100
            color = get_utilization_color(util_pct)

            # SMART ZERO-STATES: Explain WHY it's zero
            if expected_hours == 0:
                if view == "probable" and active_hours > 0:
                    cell_text = f"[dim]0h Pipeline\n({active_hours:.1f}h Active)[/dim]"
                elif view == "active" and probable_hours > 0:
                    cell_text = f"[dim]0h Active\n({probable_hours:.1f}h Pipeline)[/dim]"
                else:
                    cell_text = "[dim italic]Bench[/dim italic]"
            else:
                summary_header = f"[{color}][bold]{util_pct:.0f}%[/bold] ({expected_hours:.1f}h)[/{color}]"
                details = "\n".join(breakdown_lines)
                cell_text = f"{summary_header}\n{details}"

            row_data.append(cell_text)

        table.add_row(*row_data)
        table.add_section()

    console.print(table)

@report_app.command(name="timeline")
def report_timeline(
    interval: str = typer.Option("week", "--interval", "-i", help="Time bucket: 'day', 'week', or 'month'"),
    periods: int = typer.Option(4, "--periods", "-p", help="Number of columns to display")
    ):
    """Report: Heatmap of utilization over days, weeks, or months."""
    people = load_state(PEOPLE_FILE)
    projects = load_state(PROJECTS_FILE)
    allocations = load_state(ALLOCATIONS_FILE)

    interval = interval.lower()
    if interval not in ["day", "week", "month"]:
        typer.secho("❌ Error: Interval must be 'day', 'week', or 'month'.", fg="red")
        raise typer.Exit(code=1)

    # 1. Generate the Time Buckets (Columns)
    time_buckets = []
    current_date = datetime.now().date()

    for _ in range(periods):
        target_str = current_date.isoformat()

        if interval == "day":
            label = current_date.strftime("%b %d") # e.g., Oct 25
            next_date = current_date + timedelta(days=1)
        elif interval == "week":
            label = f"Wk {current_date.strftime('%b %d')}" # e.g., Wk Oct 25
            next_date = current_date + timedelta(days=7)
        elif interval == "month":
            label = current_date.strftime("%b %Y") # e.g., Oct 2024
            # Jump safely to the 1st of the next month
            if current_date.month == 12:
                next_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
            else:
                next_date = current_date.replace(month=current_date.month + 1, day=1)

        time_buckets.append({"label": label, "date": target_str})
        current_date = next_date

    # 2. Build the Rich Table
    table = Table(
        title=f"Utilization Timeline ({periods} {interval}s)",
        show_header=True,
        header_style="bold magenta"
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Cap.", style="dim", justify="right")

    # Add the dynamic columns!
    for bucket in time_buckets:
        table.add_column(bucket["label"], justify="center")

    # 3. Fill the Table
    for email, person_data in people.items():
        if not person_data.get("is_active", True): continue

        row_data = [
            person_data["name"],
            f"{person_data.get('capacity', 40)}h"
        ]

        # Check for Last Working Day
        exit_date = person_data.get("exit_date")
        unavailability = person_data.get("unavailability", [])

        for bucket in time_buckets:
            bucket_date = bucket["date"]

            # 1. Did they leave the company before this date?
            if exit_date and bucket_date > exit_date:
                row_data.append("[dim white]LEFT[/dim white]")
                continue

            # 2. Are they on PTO on this date?
            on_leave = False
            for leave in unavailability:
                if leave["start_date"] <= bucket_date <= leave["end_date"]:
                    on_leave = True
                    break

            if on_leave:
                row_data.append("[bold cyan]PTO[/bold cyan]")
                continue

            # 3. Standard Utilization Calculation
            util_pct = calculate_utilization_at_date(email, bucket_date, people, projects, allocations)
            color = get_utilization_color(util_pct)

            if util_pct == 0:
                row_data.append("[dim]0%[/dim]")
            else:
                row_data.append(f"[{color}]{util_pct:.0f}%[/{color}]")

        table.add_row(*row_data)

    console.print(table)

if __name__ == "__main__":
    app()
