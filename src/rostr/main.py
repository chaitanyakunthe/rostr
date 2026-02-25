import re
import uuid
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

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

# --- HELPER FUNCTIONS ---

def generate_short_code(name: str, existing_people: dict) -> str:
    """
    Generates a unique short code: 4 chars of first name + initial of last name.
    Example: 'Chaitanya Kunthe' -> 'ChaiK'.
    """
    existing_codes = {p.get("short_code", "").upper() for p in existing_people.values() if "short_code" in p}

    parts = name.strip().split()
    if not parts:
        base_code = "User"
    else:
        # First name (up to 4 chars)
        first_part = parts[0][:4]
        # Initial of last name (Uppercase)
        last_part = parts[-1][0].upper() if len(parts) > 1 else ""
        base_code = first_part + last_part

    code = base_code
    counter = 1
    # Collision resolution: Check uniqueness case-insensitively
    while code.upper() in existing_codes:
        code = f"{base_code}{counter}"
        counter += 1

    return code

def generate_project_id(name: str, existing_projects: dict) -> str:
    """Converts a Project Name into a clean, unique ID (e.g., 'My Project' -> 'my-project')."""
    base_id = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not base_id:
        base_id = "project"

    project_id = base_id
    counter = 1
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
            return ""
        try:
            valid_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            return valid_date.isoformat()
        except ValueError:
            typer.secho("⚠️ Invalid format. Please use YYYY-MM-DD (e.g., 2024-10-31).", fg="yellow")

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

            if start <= target_date <= end:
                proj_id = alloc_data["project_id"]
                project = projects.get(proj_id, {})
                proj_status = project.get("status", "Unknown")

                if proj_status not in ["Deleted", "Lost", "Completed"]:
                    probability = project.get("probability", 100)
                    weighted_hours = alloc_data["hours"] * (probability / 100.0)
                    expected_hours += weighted_hours

    return (expected_hours / base_capacity) * 100

# ==========================================
# PEOPLE COMMANDS
# ==========================================

@people_app.command(name="add")
def add_person():
    """Add new people, their capacity, designation and skills."""
    people = load_state(PEOPLE_FILE)
    email = typer.prompt("Enter email address")

    if email in people and people[email].get("is_active", True):
        typer.secho(f" ❌ Error: {email} already exists and is active!", fg="red", bold=True)
        raise typer.Exit(code=1)

    name = typer.prompt("Enter name")
    short_code = generate_short_code(name, people)
    typer.secho(f"🤖 Auto-generated short code: {short_code}", fg="cyan")

    designation = typer.prompt("Enter designation")
    capacity = typer.prompt("Enter capacity (Weekly hours)", default=40, type=int)

    skills = []
    typer.echo("---Skill Entry---")
    while True:
        skill_name = typer.prompt("Skill name (Press '.' to finish)")
        if skill_name == ".":
            break
        skill_level = typer.prompt(f"Level for {skill_name}", type=int)
        skills.append(f"{skill_name}:{skill_level}")

    payload = {
        "email": email, "name": name, "short_code": short_code,
        "designation": designation, "capacity": capacity, "skill": skills, "is_active": True
    }

    append_event("PERSON_ADDED", payload)
    typer.secho(f"\n✅ Successfully added {name} ({short_code}) to the ledger!", fg="green", bold=True)

@people_app.command(name="list")
def list_roster(
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="Filter by a specific skill"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search in emails, names, and skills")
):
    """Display all active consultants with their short codes."""
    people = load_state(PEOPLE_FILE)
    if not people:
        console.print("[yellow]The roster is currently empty.[/yellow]")
        return

    table = Table(title="Consultant Roster", header_style="bold magenta")
    table.add_column("Code", style="bold yellow")
    table.add_column("Email", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Designation", style="yellow")
    table.add_column("Capacity", justify="center", style="green")
    table.add_column("Skills", style="blue")

    for email, data in people.items():
        if not data.get("is_active", True): continue

        include = True
        if skill and not any(skill.lower() == s.split(":")[0].lower() for s in data.get("skill", [])):
            include = False
        if search and include:
            s_low = search.lower()
            if not (s_low in email.lower() or s_low in data["name"].lower() or any(s_low in s.lower() for s in data.get("skill", []))):
                include = False

        if include:
            skills_raw = data.get("skill", [])
            formatted_skills = ", ".join([s.replace(":", " (") + ")" for s in skills_raw])
            table.add_row(data.get("short_code", "??"), email, data["name"], data.get("designation", "N/A"), f"{data['capacity']}h", formatted_skills)

    console.print(table)

@people_app.command(name="edit")
def edit_person():
    """Edit a person's details, including a surgical skill update wizard."""
    people = load_state(PEOPLE_FILE)
    email = typer.prompt("Enter email of the person to edit")

    if email not in people or not people[email].get("is_active", True):
        typer.secho(f"❌ Error: {email} not found or inactive.", fg="red")
        raise typer.Exit(code=1)

    cur = people[email]
    new_name = typer.prompt("Name", default=cur["name"])
    new_code = typer.prompt("Short Code", default=cur.get("short_code", generate_short_code(new_name, people)))
    new_designation = typer.prompt("Designation", default=cur.get("designation", "N/A"))
    new_capacity = typer.prompt("Weekly capacity", default=cur["capacity"], type=int)

    # --- Skill Update Wizard ---
    skills = cur.get("skill", [])
    updated_skills = []
    if skills:
        typer.echo("\n--- Reviewing Existing Skills ---")
        for s in skills:
            s_name, s_level = s.split(":")
            styled_k = typer.style("[K]", fg=typer.colors.CYAN, bold=True)
            action = typer.prompt(f"Skill '{s_name}' (Lvl {s_level}) -> [K]eep, [U]pdate, [D]elete {styled_k}", default="K").upper()
            if action == "K": updated_skills.append(s)
            elif action == "U":
                lvl = typer.prompt(f"New level for {s_name}", type=int)
                updated_skills.append(f"{s_name}:{lvl}")
            elif action == "D": continue

    if typer.confirm("\nAdd any new skills?", default=False):
        while True:
            s_name = typer.prompt("Skill Name (Type '.' to stop)")
            if s_name == ".": break
            lvl = typer.prompt(f"Level for {s_name}", type=int)
            updated_skills.append(f"{s_name}:{lvl}")

    payload = {
        "email": email, "name": new_name, "short_code": new_code.upper(),
        "designation": new_designation, "capacity": new_capacity, "skill": updated_skills
    }

    append_event("PERSON_EDITED", payload)
    typer.secho(f"\n✅ Updated {new_name}!", fg="green", bold=True)

@people_app.command(name="timeoff")
def add_timeoff(email: Optional[str] = typer.Argument(None)):
    """Log planned unavailability (PTO, Vacation)."""
    people = load_state(PEOPLE_FILE)
    if not email: email = typer.prompt("Enter email")
    if email not in people: raise typer.Exit(1)

    start = prompt_for_date("Start Date")
    end = prompt_for_date("End Date")
    reason = typer.prompt("Reason", default="PTO")

    append_event("UNAVAILABILITY_ADDED", {"email": email, "start_date": start, "end_date": end, "reason": reason})
    typer.secho(f"✅ Logged {reason} for {people[email]['name']}.", fg="green")

@people_app.command(name="offboard")
def offboard_person(email: Optional[str] = typer.Argument(None)):
    """Set a Last Working Day for a consultant."""
    people = load_state(PEOPLE_FILE)
    if not email: email = typer.prompt("Enter email")
    if email not in people: raise typer.Exit(1)

    exit_date = prompt_for_date("Last Working Day")
    append_event("PERSON_OFFBOARDED", {"email": email, "exit_date": exit_date})
    typer.secho(f"✅ Set exit date for {people[email]['name']}.", fg="green")

@people_app.command(name="delete")
def delete_person(email: str):
    """Deactivate a person from the active roster."""
    people = load_state(PEOPLE_FILE)
    if email not in people: raise typer.Exit(1)
    if typer.confirm(f"Deactivate {people[email]['name']}?"):
        append_event("PERSON_DELETED", {"email": email})
        typer.secho("✅ Deactivated.", fg="green")

# ==========================================
# PROJECT COMMANDS
# ==========================================

@project_app.command(name="add")
def add_project():
    """Add a new project with pipeline metadata and required skills."""
    projects = load_state(PROJECTS_FILE)
    name = typer.prompt("Project Name")
    project_id = generate_project_id(name, projects)
    typer.secho(f"🤖 Auto-assigned Project ID: {project_id}", fg="cyan")

    desc = typer.prompt("Brief Description")
    status = typer.prompt("Status [Proposed/Active/Completed/Lost]", default="Proposed").capitalize()
    prob = typer.prompt("Win Probability %", type=int, default=100)

    hours_input = typer.prompt("Total hours needed (or 'TBD')", default="TBD")
    hours = int(hours_input) if hours_input.isdigit() else hours_input.strip().upper()

    req_skills = []
    typer.echo("\n--- Required Skills ---")
    while True:
        s_name = typer.prompt("Required Skill Name (Type '.' to stop)")
        if s_name == ".": break
        lvl = typer.prompt(f"Minimum Level", type=int)
        req_skills.append(f"{s_name}:{lvl}")

    append_event("PROJECT_ADDED", {
        "project_id": project_id, "name": name, "description": desc,
        "status": status, "probability": prob, "total_hours_needed": hours,
        "required_skills": req_skills
    })
    typer.secho(f"✅ Created project {project_id}.", fg="green")

@project_app.command(name="list")
def list_projects(skill: Optional[str] = typer.Option(None, "--skill", "-s")):
    """List active projects with health and skill requirements."""
    projects = load_state(PROJECTS_FILE)
    if not projects: return console.print("[yellow]Empty project list.[/yellow]")

    table = Table(title="Projects Overview", header_style="bold magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status", style="yellow")
    table.add_column("Prob %", justify="right")
    table.add_column("Hours", justify="center")
    table.add_column("Req. Skills", style="blue")

    for pid, data in projects.items():
        if data.get("status") == "Deleted": continue
        if skill and not any(skill.lower() == s.split(":")[0].lower() for s in data.get("required_skills", [])):
            continue

        skills = ", ".join([s.replace(":", " (") + ")" for s in data.get("required_skills", [])])
        raw_h = data.get("total_hours_needed", "TBD")
        h_disp = f"{raw_h}h" if str(raw_h).isdigit() else str(raw_h)

        table.add_row(pid, data["name"], data.get("status", "N/A"), f"{data.get('probability', 100)}%", h_disp, skills)
    console.print(table)

@project_app.command(name="edit")
def edit_project():
    """Edit a project's metadata and required skills."""
    projects = load_state(PROJECTS_FILE)
    pid = typer.prompt("Enter Project ID to edit")
    if pid not in projects or projects[pid].get("status") == "Deleted":
        raise typer.Exit(1)

    cur = projects[pid]
    name = typer.prompt("Name", default=cur["name"])
    desc = typer.prompt("Description", default=cur.get("description", ""))
    status = typer.prompt("Status", default=cur.get("status", "Proposed")).capitalize()
    prob = typer.prompt("Win Probability %", type=int, default=cur.get("probability", 100))

    # Skill wizard for projects
    req_skills = cur.get("required_skills", [])
    updated_reqs = []
    if req_skills:
        for s in req_skills:
            s_name, s_level = s.split(":")
            action = typer.prompt(f"Req Skill '{s_name}' (Lvl {s_level}) -> [K]eep, [U]pdate, [D]elete", default="K").upper()
            if action == "K": updated_reqs.append(s)
            elif action == "U":
                lvl = typer.prompt(f"New level", type=int)
                updated_reqs.append(f"{s_name}:{lvl}")
            elif action == "D": continue

    if typer.confirm("\nAdd any new required skills?", default=False):
        while True:
            s_name = typer.prompt("Skill ('.' to stop)")
            if s_name == ".": break
            lvl = typer.prompt(f"Min Lvl", type=int)
            updated_reqs.append(f"{s_name}:{lvl}")

    append_event("PROJECT_EDITED", {
        "project_id": pid, "name": name, "description": desc,
        "status": status, "probability": prob, "required_skills": updated_reqs
    })
    typer.secho("✅ Updated project.", fg="green")

@project_app.command(name="allocate")
def allocate_person(project_id: Optional[str] = typer.Argument(None)):
    """Staff a consultant to a project with a skill-matching visualizer."""
    projects = load_state(PROJECTS_FILE)
    people = load_state(PEOPLE_FILE)
    if not project_id: project_id = typer.prompt("Project ID")
    if project_id not in projects: raise typer.Exit(1)

    reqs = projects[project_id].get("required_skills", [])
    def is_match(p_skills, r_skills):
        if not r_skills: return True
        p_dict = {s.split(":")[0].lower(): int(s.split(":")[1]) for s in p_skills}
        for r in r_skills:
            rn, rl = r.split(":")
            if p_dict.get(rn.lower(), 0) < int(rl): return False
        return True

    typer.echo(f"\n--- Staffing Visualizer: {projects[project_id]['name']} ---")
    table = Table(header_style="bold magenta")
    table.add_column("Match", justify="center")
    table.add_column("Code", style="yellow")
    table.add_column("Name")
    for email, data in people.items():
        if not data.get("is_active", True): continue
        icon = "✅" if is_match(data.get("skill", []), reqs) else "❌"
        table.add_row(icon, data.get("short_code", "??"), data['name'])
    console.print(table)

    email = typer.prompt("\nEnter Email")
    if email not in people: raise typer.Exit(1)

    hours = typer.prompt("Weekly Hours", type=int)
    is_lead = typer.confirm(f"Is {people[email]['name']} the Lead?", default=False)
    start = prompt_for_date("Start Date")
    end = prompt_for_date("End Date (Enter for 1 year)", allow_empty=True)
    if not end: end = (datetime.strptime(start, "%Y-%m-%d") + timedelta(days=365)).date().isoformat()

    append_event("ALLOCATION_ADDED", {
        "allocation_id": uuid.uuid4().hex[:8], "project_id": project_id,
        "email": email, "hours": hours, "is_lead": is_lead,
        "start_date": start, "end_date": end
    })
    typer.secho("✅ Allocated consultant.", fg="green")

@project_app.command(name="unallocate")
def unallocate_person():
    """Remove a specific consultant allocation."""
    allocs = load_state(ALLOCATIONS_FILE)
    projects = load_state(PROJECTS_FILE)
    if not allocs: return typer.echo("No active allocations.")

    table = Table(title="Allocations")
    table.add_column("ID", style="dim")
    table.add_column("Project")
    table.add_column("Consultant")
    for aid, data in allocs.items():
        p_name = projects.get(data['project_id'], {}).get('name', '???')
        table.add_row(aid, p_name, data['email'])
    console.print(table)
    aid = typer.prompt("Enter ID to remove")
    if aid in allocs:
        append_event("ALLOCATION_REMOVED", {"allocation_id": aid})
        typer.secho("✅ Removed.", fg="green")

# ==========================================
# REPORT COMMANDS
# ==========================================

@report_app.command(name="current")
def report_current():
    """Real-time utilization snapshot."""
    people = load_state(PEOPLE_FILE)
    projects = load_state(PROJECTS_FILE)
    allocs = load_state(ALLOCATIONS_FILE)
    today = datetime.now().date().isoformat()

    table = Table(title=f"Current Utilization ({today})", header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Util.", justify="right")
    table.add_column("Breakdown")

    for email, p in people.items():
        if not p.get("is_active", True): continue
        cap = p.get("capacity", 40)
        total_h, breakdown = 0, []
        for aid, d in allocs.items():
            if d["email"] == email and d["start_date"] <= today <= d.get("end_date", "9999-12-31"):
                proj = projects.get(d["project_id"], {})
                if proj.get("status") not in ["Deleted", "Lost", "Completed"]:
                    total_h += d["hours"]
                    breakdown.append(f"• {proj['name']}: {d['hours']}h")

        util = (total_h / cap) * 100 if cap > 0 else 0
        color = get_utilization_color(util)
        table.add_row(p["name"], f"[{color}]{util:.0f}%[/{color}]", "\n".join(breakdown) if breakdown else "[dim]Bench[/dim]")
        table.add_section()
    console.print(table)

@report_app.command(name="forecast")
def report_forecast(months: int = typer.Option(3, "--months", "-m", help="Number of months to forecast")):
    """Predict future utilization based on pipeline probability."""
    people = load_state(PEOPLE_FILE)
    projects = load_state(PROJECTS_FILE)
    allocs = load_state(ALLOCATIONS_FILE)

    buckets = []
    curr = datetime.now().date()
    for _ in range(months):
        target = (curr.replace(day=28) + timedelta(days=4)).replace(day=15)
        buckets.append({"label": target.strftime("%b %Y"), "date": target.isoformat()})
        curr = target

    table = Table(title=f"{months}-Month Weighted Forecast")
    table.add_column("Name", style="cyan")
    for b in buckets: table.add_column(b["label"])

    for email, p in people.items():
        if not p.get("is_active", True): continue
        row = [p["name"]]
        for b in buckets:
            weighted_h = 0.0
            for d in allocs.values():
                if d["email"] == email and d["start_date"] <= b["date"] <= d.get("end_date", "9999"):
                    proj = projects.get(d["project_id"], {})
                    if proj.get("status") not in ["Deleted", "Lost", "Completed"]:
                        weighted_h += d["hours"] * (proj.get("probability", 100) / 100.0)
            util = (weighted_h / p.get('capacity', 40)) * 100
            color = get_utilization_color(util)
            row.append(f"[{color}]{util:.0f}%[/{color}]\n({weighted_h:.1f}h)")
        table.add_row(*row)
        table.add_section()
    console.print(table)

@report_app.command(name="timeline")
def report_timeline(
    interval: str = typer.Option("week", "--interval", "-i", help="Interval: day, week, month"),
    periods: int = typer.Option(4, "--periods", "-p", help="Number of time periods to display")
):
    """Consultant utilization heatmap."""
    people = load_state(PEOPLE_FILE)
    projects = load_state(PROJECTS_FILE)
    allocs = load_state(ALLOCATIONS_FILE)
    buckets = []
    curr = datetime.now().date()
    for _ in range(periods):
        start = curr
        if interval == "day":
            end = curr + timedelta(days=1)
            label = start.strftime('%m/%d')
        elif interval == "week":
            end = curr + timedelta(days=7)
            label = f"W{start.strftime('%m/%d')}"
        else: # month
            end = (curr.replace(day=28) + timedelta(days=4)).replace(day=1)
            label = start.strftime('%b %y')

        buckets.append({"l": label, "s": start.isoformat(), "e": end.isoformat()})
        curr = end

    table = Table(title="Consultant Heatmap", header_style="bold magenta")
    table.add_column("Code", style="bold yellow")
    table.add_column("Name", style="cyan")
    for b in buckets: table.add_column(b["l"], justify="center")

    for email, pdata in people.items():
        if not pdata.get("is_active", True): continue
        row = [pdata.get("short_code", "??"), pdata["name"]]
        for b in buckets:
            if pdata.get("exit_date") and b["s"] > pdata["exit_date"]: row.append("[dim]LEFT[/]")
            elif any(l['start_date'] < b['e'] and l['end_date'] >= b['s'] for l in pdata.get('unavailability', [])):
                row.append("[bold cyan]PTO[/]")
            else:
                util = calculate_utilization_at_date(email, b["s"], people, projects, allocs)
                row.append(f"[{get_utilization_color(util)}]{util:.0f}%[/]" if util > 0 else "[dim].[/]")
        table.add_row(*row)
    console.print(table)

@report_app.command(name="summary")
def report_summary(
    interval: str = typer.Option("week", "--interval", "-i", help="Interval: day, week, month"),
    periods: int = typer.Option(4, "--periods", "-p", help="Number of time periods to display")
):
    """Project-centric report with dates, lead, team, and resource breakdown."""
    people = load_state(PEOPLE_FILE)
    projects = load_state(PROJECTS_FILE)
    allocs = load_state(ALLOCATIONS_FILE)
    buckets = []
    curr = datetime.now().date()
    for _ in range(periods):
        start = curr
        if interval == "day":
            end = curr + timedelta(days=1)
            label = start.strftime('%m/%d')
        elif interval == "week":
            end = curr + timedelta(days=7)
            label = f"W{start.strftime('%m/%d')}"
        else: # month
            end = (curr.replace(day=28) + timedelta(days=4)).replace(day=1)
            label = start.strftime('%b %y')

        buckets.append({"l": label, "s": start.isoformat(), "e": end.isoformat()})
        curr = end

    table = Table(title="Project Allocation Summary", header_style="bold magenta")
    table.add_column("Project", style="cyan")
    table.add_column("Dates / Status", style="dim")
    table.add_column("Lead", style="yellow")
    for b in buckets: table.add_column(b["l"], justify="center")

    for pid, pdata in projects.items():
        if pdata.get("status") == "Deleted": continue
        p_allocs = [a for a in allocs.values() if a.get('project_id') == pid]
        starts = [a['start_date'] for a in p_allocs if a.get('start_date')]
        ends = [a['end_date'] for a in p_allocs if a.get('end_date')]
        p_start = min(starts) if starts else "??"
        p_end = max(ends) if ends else "??"

        lead = "N/A"
        for a in p_allocs:
            if a.get('is_lead'):
                lead = people.get(a['email'], {}).get('name', a['email'])
                break

        row = [f"{pdata['name']}", f"{p_start} -> {p_end}\n[italic]{pdata.get('status', 'Active')}[/italic]", lead]
        for b in buckets:
            bucket_res = {}
            for a in p_allocs:
                if a['start_date'] < b['e'] and a.get('end_date', '9999-12-31') >= b['s']:
                    p_info = people.get(a['email'], {})
                    code = p_info.get("short_code", p_info.get("name", a['email']))
                    bucket_res[code] = bucket_res.get(code, 0) + a['hours']

            if bucket_res:
                items = [f"{code}: {hrs}h" for code, hrs in sorted(bucket_res.items())]
                row.append("\n".join(items) + f"\n[dim]--[/]\n[bold]Tot: {sum(bucket_res.values())}h[/]")
            else:
                row.append("[dim].[/]")
        table.add_row(*row)
        table.add_section()
    console.print(table)

@report_app.command(name="skills")
def report_skill_gap():
    """Identify organizational shortages based on project requirements."""
    projects = load_state(PROJECTS_FILE)
    people = load_state(PEOPLE_FILE)
    reqs, avails = {}, {}
    for p in projects.values():
        if p.get("status") in ["Active", "Proposed"]:
            for s in p.get("required_skills", []):
                n, l = s.split(":")
                reqs[n] = max(reqs.get(n, 0), int(l))
    for p in people.values():
        if p.get("is_active", True):
            for s in p.get("skill", []):
                n, l = s.split(":")
                avails[n] = max(avails.get(n, 0), int(l))

    table = Table(title="Skill Gap Analysis")
    table.add_column("Skill")
    table.add_column("Max Req.", justify="center")
    table.add_column("Max Avail.", justify="center")
    table.add_column("Status")
    for skill, rl in reqs.items():
        al = avails.get(skill, 0)
        status = "[green]✅ Covered[/]" if al >= rl else "[red]⚠️ GAP[/]"
        table.add_row(skill, str(rl), str(al), status)
    console.print(table)

if __name__ == "__main__":
    app()
