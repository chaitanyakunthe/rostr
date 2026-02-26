import re
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

# Relative import for our local ledger module
from .ledger import append_event, load_state, PEOPLE_FILE, PROJECTS_FILE, ALLOCATIONS_FILE

# Initialize the Main App and Sub-Apps
app = typer.Typer(help="Rostr: Resource and Project Management CLI", add_completion=False)
people_app = typer.Typer(help="Manage consultants, skills, and availability")
project_app = typer.Typer(help="Manage projects and staffing allocations")
report_app = typer.Typer(help="Generate utilization, forecast, and gap reports")

app.add_typer(people_app, name="people")
app.add_typer(project_app, name="project")
app.add_typer(report_app, name="report")

console = Console()

# --- HELPER FUNCTIONS ---

def calculate_dynamic_experience(stored_exp: float, update_date_str: Optional[str]) -> float:
    """
    Calculates the current years of experience based on the date the value was last recorded.
    Ensures that experience 'grows' automatically as time passes.
    """
    if not update_date_str:
        return stored_exp
    try:
        update_date = datetime.strptime(update_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        # Use 365.25 to account for leap years over long durations
        delta_days = (today - update_date).days
        years_elapsed = delta_days / 365.25
        return round(stored_exp + years_elapsed, 1)
    except (ValueError, TypeError):
        return stored_exp

def generate_short_code(name: str, existing_people: Dict[str, Any]) -> str:
    """
    Standard: First 4 letters of first name + Initial of last name.
    Example: 'Chaitanya Kunthe' -> 'ChaiK'. Handles collisions with suffixes.
    """
    existing_codes = {p.get("short_code", "").upper() for p in existing_people.values() if "short_code" in p}
    parts = name.strip().split()
    if not parts:
        base_code = "CONS"
    else:
        first_part = parts[0][:4].capitalize()
        last_part = parts[-1][0].upper() if len(parts) > 1 else ""
        base_code = first_part + last_part

    code = base_code
    counter = 1
    while code.upper() in existing_codes:
        code = f"{base_code}{counter}"
        counter += 1
    return code

def generate_project_short_code(name: str, existing_projects: Dict[str, Any]) -> str:
    """
    Standard: First 6 letters of first word + Initial of last word.
    Example: 'Digital Transformation Phase 1' -> 'Digita1'. Handles collisions.
    """
    existing_codes = {p.get("short_code", "").upper() for p in existing_projects.values() if "short_code" in p}
    parts = name.strip().split()
    if not parts:
        base_code = "PROJ"
    else:
        first_part = parts[0][:6].capitalize()
        last_part = parts[-1][0].upper() if len(parts) > 1 else ""
        base_code = first_part + last_part

    code = base_code
    counter = 1
    while code.upper() in existing_codes:
        suffix = str(counter)
        # Ensure we stay within a reasonable character limit for UI
        code = base_code[:8-len(suffix)] + suffix
        counter += 1
    return code

def generate_project_id(name: str, existing_projects: Dict[str, Any]) -> str:
    """Converts a Project Name into a unique URL-friendly slug ID."""
    base_id = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not base_id: base_id = "project"
    project_id, counter = base_id, 1
    while project_id in existing_projects:
        counter += 1
        project_id = f"{base_id}-{counter}"
    return project_id

def prompt_for_date(prompt_text: str, allow_empty: bool = False) -> str:
    """Forces valid YYYY-MM-DD date entry with optional skip support."""
    prompt_str = f"{prompt_text} (YYYY-MM-DD)"
    if allow_empty:
        prompt_str += typer.style(" [Press Enter to skip]", fg=typer.colors.CYAN)
    while True:
        date_str = typer.prompt(prompt_str, default="", show_default=False).strip()
        if allow_empty and not date_str: return ""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
        except ValueError:
            typer.secho("⚠️ Invalid format. Please use YYYY-MM-DD (e.g., 2025-12-31).", fg="yellow")

def get_utilization_color(utilization_pct: float) -> str:
    """Color palette for utilization levels."""
    if utilization_pct > 100: return "red"
    if utilization_pct >= 75: return "green"
    return "yellow"

def calculate_utilization_at_date(email: str, target_date: str, people: dict, projects: dict, allocations: dict) -> float:
    """Calculates weighted utilization percentage for a specific date, factoring in pipeline probability."""
    person_data = people.get(email, {})
    base_capacity = person_data.get("capacity", 40)
    if base_capacity <= 0: return 0.0

    expected_hours = 0.0
    for alloc in allocations.values():
        if alloc["email"] == email:
            start, end = alloc["start_date"], alloc.get("end_date", "2099-12-31")
            if start <= target_date <= end:
                proj = projects.get(alloc["project_id"], {})
                # Skip projects that are no longer in scope
                if proj.get("status") not in ["Deleted", "Lost", "Completed"]:
                    prob = proj.get("probability", 100)
                    expected_hours += alloc["hours"] * (prob / 100.0)
    return (expected_hours / base_capacity) * 100

# ==========================================
# PEOPLE COMMANDS
# ==========================================

@people_app.command(name="add")
def add_person():
    """Register a new consultant with auto-shortcode and dynamic experience tracking."""
    people = load_state(PEOPLE_FILE)
    email = typer.prompt("Enter email address")
    if email in people and people[email].get("is_active", True):
        typer.secho(f"❌ Error: {email} is already active in the roster!", fg="red", bold=True)
        raise typer.Exit(code=1)

    name = typer.prompt("Enter Full Name")
    short_code = generate_short_code(name, people)
    typer.secho(f"🤖 Auto-assigned Short Code: {short_code}", fg="cyan")

    designation = typer.prompt("Designation (e.g. Lead Engineer)")
    capacity = typer.prompt("Weekly Hours Capacity", default=40, type=int)
    experience = typer.prompt("Total Years of Experience (to date)", default=0.0, type=float)

    skills = []
    typer.echo("\n--- Skills Entry (Enter '.' as skill name to finish) ---")
    while True:
        s_name = typer.prompt("Skill name")
        if s_name == ".": break
        s_level = typer.prompt(f"Level for {s_name} (1-10)", type=int)
        skills.append(f"{s_name}:{s_level}")

    payload = {
        "email": email, "name": name, "short_code": short_code,
        "designation": designation, "capacity": capacity,
        "experience": experience,
        "experience_updated_at": datetime.now().date().isoformat(),
        "skill": skills, "is_active": True
    }
    append_event("PERSON_ADDED", payload)
    typer.secho(f"\n✅ Successfully added {name} ({short_code}) to the roster!", fg="green", bold=True)

@people_app.command(name="list")
def list_people(
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="Filter by specific skill"),
    search: Optional[str] = typer.Option(None, "--search", "-q", help="Search name, email, or skills")
):
    """View the active consultant roster with auto-calculated experience."""
    people = load_state(PEOPLE_FILE)
    if not people: return console.print("[yellow]The roster is currently empty.[/yellow]")

    table = Table(title="Consultant Roster", header_style="bold magenta")
    table.add_column("Code", style="bold yellow")
    table.add_column("Email", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Designation", style="yellow")
    table.add_column("Exp (Now)", justify="center", style="magenta")
    table.add_column("Skills", style="blue")

    for email, data in people.items():
        if not data.get("is_active", True): continue

        if skill and not any(skill.lower() == s.split(":")[0].lower() for s in data.get("skill", [])): continue
        if search and not (search.lower() in f"{email} {data['name']} {' '.join(data.get('skill', []))}".lower()): continue

        cur_exp = calculate_dynamic_experience(data.get("experience", 0.0), data.get("experience_updated_at"))
        skills_raw = data.get("skill", [])
        fmt_skills = ", ".join([s.replace(":", " (") + ")" for s in skills_raw])

        table.add_row(
            data.get("short_code", "??"), email, data["name"],
            data.get("designation", "N/A"), f"{cur_exp}y", fmt_skills if fmt_skills else "No skills logged"
        )
    console.print(table)

@people_app.command(name="edit")
def edit_person():
    """Update consultant details, base experience, or modify skills surgically."""
    people = load_state(PEOPLE_FILE)

    # Cheat sheet for easy lookup
    ref_table = Table(title="Reference: Active Consultants")
    ref_table.add_column("Code"); ref_table.add_column("Email"); ref_table.add_column("Name")
    for e, d in people.items():
        if d.get("is_active", True): ref_table.add_row(d.get("short_code", "??"), e, d["name"])
    console.print(ref_table)

    email = typer.prompt("\nEnter email of the person to edit")
    if email not in people or not people[email].get("is_active", True):
        typer.secho("❌ Error: Active consultant not found.", fg="red")
        raise typer.Exit(1)

    cur = people[email]
    new_name = typer.prompt("Full Name", default=cur["name"])
    new_code = typer.prompt("Short Code", default=cur.get("short_code", generate_short_code(new_name, people)))
    new_desig = typer.prompt("Designation", default=cur.get("designation", "N/A"))
    new_cap = typer.prompt("Weekly Hours", default=cur["capacity"], type=int)

    calc_exp = calculate_dynamic_experience(cur.get("experience", 0.0), cur.get("experience_updated_at"))
    new_exp = typer.prompt("Update Years of Experience", default=calc_exp, type=float)

    # Surgical Skill Update Wizard
    current_skills = cur.get("skill", [])
    updated_skills = []
    if current_skills:
        typer.echo("\n--- Skill Review ---")
        for s in current_skills:
            name, level = s.split(":")
            styled_k = typer.style("[K]", fg=typer.colors.CYAN, bold=True)
            action = typer.prompt(f"'{name}' (Lvl {level}) -> [K]eep, [U]pdate, [D]elete {styled_k}", default="K").upper()
            if action == "K": updated_skills.append(s)
            elif action == "U":
                lvl = typer.prompt(f"New level for {name}", type=int); updated_skills.append(f"{name}:{lvl}")
            elif action == "D": continue

    if typer.confirm("\nAdd any new skills?", default=False):
        while True:
            sn = typer.prompt("Skill ('.' to finish)");
            if sn == ".": break
            sl = typer.prompt("Level (1-10)", type=int); updated_skills.append(f"{sn}:{sl}")

    append_event("PERSON_EDITED", {
        "email": email, "name": new_name, "short_code": new_code.upper(),
        "designation": new_desig, "capacity": new_cap, "experience": new_exp,
        "experience_updated_at": datetime.now().date().isoformat(), "skill": updated_skills
    })
    typer.secho(f"✅ Successfully updated {new_name} in the ledger!", fg="green")

@people_app.command(name="timeoff")
def add_timeoff(email: Optional[str] = typer.Argument(None)):
    """Log upcoming leave, vacation, or PTO."""
    people = load_state(PEOPLE_FILE)
    if not email:
        email = typer.prompt("Consultant email")
    if email not in people:
        typer.secho("❌ Email not found.", fg="red"); raise typer.Exit(1)

    start = prompt_for_date("Leave Start Date")
    end = prompt_for_date("Leave End Date")
    reason = typer.prompt("Reason (e.g. PTO, Training)", default="PTO")

    append_event("UNAVAILABILITY_ADDED", {"email": email, "start_date": start, "end_date": end, "reason": reason})
    typer.secho(f"✅ Logged {reason} for {people[email]['name']}.", fg="green")

@people_app.command(name="offboard")
def offboard_person(email: Optional[str] = typer.Argument(None)):
    """Set the Last Working Day for a departing consultant."""
    people = load_state(PEOPLE_FILE)
    if not email: email = typer.prompt("Consultant email")
    if email not in people: raise typer.Exit(1)

    exit_date = prompt_for_date("Last Working Day")
    append_event("PERSON_OFFBOARDED", {"email": email, "exit_date": exit_date})
    typer.secho(f"✅ Offboarding scheduled for {exit_date}.", fg="green")

@people_app.command(name="delete")
def delete_person(email: str):
    """Deactivate a consultant from the active roster."""
    people = load_state(PEOPLE_FILE)
    if email not in people: raise typer.Exit(1)
    if typer.confirm(f"Are you sure you want to deactivate {people[email]['name']}?"):
        append_event("PERSON_DELETED", {"email": email})
        typer.secho("✅ Deactivated successfully.", fg="green")

# ==========================================
# PROJECT COMMANDS
# ==========================================

@project_app.command(name="add")
def add_project():
    """Create a new project with short-codes, unique IDs, and health metadata."""
    projects = load_state(PROJECTS_FILE)
    name = typer.prompt("Project Name")
    project_id = generate_project_id(name, projects)

    short_code = generate_project_short_code(name, projects)
    typer.secho(f"🤖 Auto-assigned Short Code: {short_code}", fg="cyan")

    unique_code = typer.prompt("Project Unique Code (Optional internal ID)", default="", show_default=False)
    desc = typer.prompt("Brief Description")
    status = typer.prompt("Status [Proposed/Active/Completed/Lost]", default="Proposed").capitalize()
    prob = typer.prompt("Win Probability %", type=int, default=100)

    req_skills = []
    typer.echo("\n--- Required Skills (Enter '.' to finish) ---")
    while True:
        sn = typer.prompt("Required Skill")
        if sn == ".": break
        sl = typer.prompt(f"Min Level for {sn}", type=int); req_skills.append(f"{sn}:{sl}")

    append_event("PROJECT_ADDED", {
        "project_id": project_id, "name": name, "short_code": short_code,
        "unique_code": unique_code, "description": desc, "status": status,
        "probability": prob, "required_skills": req_skills
    })
    typer.secho(f"✅ Project {project_id} recorded in ledger.", fg="green")

@project_app.command(name="list")
def list_projects(skill: Optional[str] = typer.Option(None, "--skill", "-s")):
    """Overview of all active projects with health, requirements, and assigned team."""
    projects = load_state(PROJECTS_FILE)
    people = load_state(PEOPLE_FILE)
    allocations = load_state(ALLOCATIONS_FILE)

    if not projects: return console.print("[yellow]The project list is empty.[/yellow]")

    table = Table(title="Projects Overview", header_style="bold magenta")
    table.add_column("S-Code", style="bold yellow")
    table.add_column("U-Code", style="dim")
    table.add_column("Name", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Prob %", justify="right")
    table.add_column("Team", style="cyan")
    table.add_column("Required Skills", style="blue")

    for pid, data in projects.items():
        if data.get("status") == "Deleted": continue
        if skill and not any(skill.lower() == s.split(":")[0].lower() for s in data.get("required_skills", [])): continue

        # Get team assigned to this project
        assigned_team = []
        for a in allocations.values():
            if a.get("project_id") == pid:
                p_info = people.get(a["email"], {})
                code = p_info.get("short_code", p_info.get("name", a["email"]))
                display_name = f"{code}*" if a.get("is_lead") else code
                assigned_team.append(display_name)

        team_str = ", ".join(sorted(assigned_team)) if assigned_team else "[dim]-[/dim]"
        skills = ", ".join([s.replace(":", " (") + ")" for s in data.get("required_skills", [])])

        table.add_row(
            data.get("short_code", "??"), data.get("unique_code", "-"),
            data["name"], data.get("status", "N/A"), f"{data.get('probability', 100)}%",
            team_str, skills
        )
    console.print(table)

@project_app.command(name="edit")
def edit_project():
    """Modify project metadata, codes, and staffing requirements."""
    projects = load_state(PROJECTS_FILE)

    # Reference
    ref = Table(title="Reference: Projects")
    ref.add_column("S-Code"); ref.add_column("Slug ID"); ref.add_column("Name")
    for pid, d in projects.items():
        if d.get("status") != "Deleted": ref.add_row(d.get("short_code", "??"), pid, d["name"])
    console.print(ref)

    pid = typer.prompt("\nEnter Project Slug ID to edit")
    if pid not in projects or projects[pid].get("status") == "Deleted":
        typer.secho("❌ Project not found.", fg="red"); raise typer.Exit(1)

    cur = projects[pid]
    name = typer.prompt("Name", default=cur["name"])
    short_code = typer.prompt("Short Code", default=cur.get("short_code", generate_project_short_code(name, projects)))
    unique_code = typer.prompt("Unique Code", default=cur.get("unique_code", ""))
    desc = typer.prompt("Description", default=cur.get("description", ""))
    status = typer.prompt("Status", default=cur.get("status", "Proposed")).capitalize()
    prob = typer.prompt("Win Probability %", type=int, default=cur.get("probability", 100))

    # Requirement Wizard
    reqs = cur.get("required_skills", [])
    updated_reqs = []
    if reqs:
        for s in reqs:
            sn, sl = s.split(":")
            action = typer.prompt(f"Requirement '{sn}' (Lvl {sl}) -> [K]eep, [U]pdate, [D]elete", default="K").upper()
            if action == "K": updated_reqs.append(s)
            elif action == "U":
                lvl = typer.prompt("New min level", type=int); updated_reqs.append(f"{sn}:{lvl}")
            elif action == "D": continue

    if typer.confirm("\nAdd new requirements?", default=False):
        while True:
            sn = typer.prompt("Skill ('.' to stop)");
            if sn == ".": break
            sl = typer.prompt("Min Level", type=int); updated_reqs.append(f"{sn}:{sl}")

    append_event("PROJECT_EDITED", {
        "project_id": pid, "name": name, "short_code": short_code.upper(),
        "unique_code": unique_code, "description": desc, "status": status,
        "probability": prob, "required_skills": updated_reqs
    })
    typer.secho("✅ Project updated.", fg="green")

@project_app.command(name="allocate")
def allocate_person():
    """Fast staffing using short-codes for projects and consultants."""
    projects, people = load_state(PROJECTS_FILE), load_state(PEOPLE_FILE)

    # 1. Project Selection
    ptable = Table(title="Available Projects", header_style="bold magenta")
    ptable.add_column("S-Code", style="bold yellow"); ptable.add_column("Name"); ptable.add_column("Status")
    scode_to_pid = {}
    for pid, d in projects.items():
        if d.get("status") == "Deleted": continue
        sc = d.get("short_code", "??").upper()
        scode_to_pid[sc] = pid
        ptable.add_row(d.get("short_code", "??"), d["name"], d.get("status", "Active"))
    console.print(ptable)

    p_code = typer.prompt("\nEnter Project Short Code").upper()
    if p_code not in scode_to_pid:
        typer.secho("❌ Project code not found.", fg="red"); raise typer.Exit(1)

    project_id = scode_to_pid[p_code]
    reqs = projects[project_id].get("required_skills", [])

    def is_match(ps, rs):
        if not rs: return True
        pd = {s.split(":")[0].lower(): int(s.split(":")[1]) for s in ps}
        for r in rs:
            rn, rl = r.split(":")
            if pd.get(rn.lower(), 0) < int(rl): return False
        return True

    # 2. Consultant Selection
    ctable = Table(title=f"Staffing Visualizer: {projects[project_id]['name']}", header_style="bold magenta")
    ctable.add_column("Match", justify="center"); ctable.add_column("Code", style="bold yellow")
    ctable.add_column("Name"); ctable.add_column("Exp"); ctable.add_column("Designation")
    scode_to_email = {}
    for email, d in people.items():
        if not d.get("is_active", True): continue
        sc = d.get("short_code", "??").upper()
        scode_to_email[sc] = email
        icon = "✅" if is_match(d.get("skill", []), reqs) else "❌"
        exp = calculate_dynamic_experience(d.get("experience", 0.0), d.get("experience_updated_at"))
        ctable.add_row(icon, d.get("short_code", "??"), d["name"], f"{exp}y", d.get("designation", "N/A"))
    console.print(ctable)

    c_code = typer.prompt("\nEnter Consultant Short Code").upper()
    if c_code not in scode_to_email:
        typer.secho("❌ Consultant code not found.", fg="red"); raise typer.Exit(1)
    email = scode_to_email[c_code]

    # 3. Allocation Data
    hours = typer.prompt("Weekly Hours committed", type=int)
    is_lead = typer.confirm("Is this person the Project Lead?", default=False)
    start = prompt_for_date("Start Date")
    end = prompt_for_date("End Date (Enter for 1 year default)", allow_empty=True)
    if not end: end = (datetime.strptime(start, "%Y-%m-%d") + timedelta(days=365)).date().isoformat()

    append_event("ALLOCATION_ADDED", {
        "allocation_id": uuid.uuid4().hex[:8], "project_id": project_id,
        "email": email, "hours": hours, "is_lead": is_lead,
        "start_date": start, "end_date": end
    })
    typer.secho(f"✅ Successfully allocated {people[email]['name']} to project!", fg="green", bold=True)

@project_app.command(name="unallocate")
def unallocate_person():
    """Remove a consultant allocation from a project."""
    allocs, projects = load_state(ALLOCATIONS_FILE), load_state(PROJECTS_FILE)
    if not allocs: return typer.echo("No active allocations to remove.")

    table = Table(title="Current Staffing Allocations")
    table.add_column("ID", style="dim"); table.add_column("Project"); table.add_column("Consultant")
    for aid, d in allocs.items():
        pname = projects.get(d['project_id'], {}).get('name', '???')
        table.add_row(aid, pname, d['email'])
    console.print(table)

    aid = typer.prompt("\nEnter Allocation ID to remove")
    if aid in allocs:
        append_event("ALLOCATION_REMOVED", {"allocation_id": aid})
        typer.secho("✅ Allocation removed.", fg="green")
    else:
        typer.secho("❌ ID not found.", fg="red")

# ==========================================
# REPORT COMMANDS
# ==========================================

@report_app.command(name="current")
def report_current():
    """Snapshot of current utilization across the whole team."""
    people, projects, allocs = load_state(PEOPLE_FILE), load_state(PROJECTS_FILE), load_state(ALLOCATIONS_FILE)
    today = datetime.now().date().isoformat()

    table = Table(title=f"Team Utilization Summary ({today})", header_style="bold magenta")
    table.add_column("Code", style="bold yellow"); table.add_column("Name", style="cyan")
    table.add_column("Cap.", justify="right", style="dim"); table.add_column("Util.", justify="right")
    table.add_column("Active Projects", style="blue")

    for email, p in people.items():
        if not p.get("is_active", True): continue
        total_h, details = 0, []
        for d in allocs.values():
            if d["email"] == email and d["start_date"] <= today <= d.get("end_date", "9999-12-31"):
                proj = projects.get(d["project_id"], {})
                if proj.get("status") not in ["Deleted", "Lost", "Completed"]:
                    total_h += d["hours"]; details.append(f"{proj['name']} ({d['hours']}h)")

        util = (total_h / p.get("capacity", 40)) * 100
        color = get_utilization_color(util)
        breakdown = ", ".join(details) if details else "[italic magenta]Bench[/italic magenta]"

        table.add_row(p.get("short_code", "??"), p["name"], f"{p['capacity']}h", f"[{color}]{util:.0f}%[/]", breakdown)
    console.print(table)

@report_app.command(name="forecast")
def report_forecast(months: int = typer.Option(3, "--months", "-m", help="Months to predict")):
    """Pipeline-aware multi-month utilization projection."""
    people, projects, allocs = load_state(PEOPLE_FILE), load_state(PROJECTS_FILE), load_state(ALLOCATIONS_FILE)

    buckets = []
    curr = datetime.now().date()
    for _ in range(months):
        target = (curr.replace(day=28) + timedelta(days=4)).replace(day=15)
        buckets.append({"label": target.strftime("%b %y"), "date": target.isoformat()}); curr = target

    table = Table(title=f"{months}-Month Probability Forecast", header_style="bold magenta")
    table.add_column("Code", style="bold yellow"); table.add_column("Name", style="cyan")
    for b in buckets: table.add_column(b["label"], justify="center")

    for email, p in people.items():
        if not p.get("is_active", True): continue
        row = [p.get("short_code", "??"), p["name"]]
        for b in buckets:
            weighted_h = 0.0
            for d in allocs.values():
                if d["email"] == email and d["start_date"] <= b["date"] <= d.get("end_date", "9999"):
                    proj = projects.get(d["project_id"], {})
                    if proj.get("status") not in ["Deleted", "Lost", "Completed"]:
                        weighted_h += d["hours"] * (proj.get("probability", 100) / 100.0)

            util = (weighted_h / p.get('capacity', 40)) * 100
            color = get_utilization_color(util)
            row.append(f"[{color}]{util:.0f}%[/] ({weighted_h:.1f}h)")
        table.add_row(*row)
    console.print(table)

@report_app.command(name="timeline")
def report_timeline(
    interval: str = typer.Option("week", "--interval", "-i"),
    periods: int = typer.Option(4, "--periods", "-p")
):
    """Heatmap displaying utilization and leave (PTO) overlaps."""
    people, projects, allocs = load_state(PEOPLE_FILE), load_state(PROJECTS_FILE), load_state(ALLOCATIONS_FILE)

    buckets = []
    curr = datetime.now().date()
    for _ in range(periods):
        start = curr
        if interval == "day": end = curr + timedelta(days=1); label = start.strftime('%m/%d')
        elif interval == "week": end = curr + timedelta(days=7); label = f"W{start.strftime('%m/%d')}"
        else: end = (curr.replace(day=28) + timedelta(days=4)).replace(day=1); label = start.strftime('%b %y')
        buckets.append({"l": label, "s": start.isoformat(), "e": end.isoformat()}); curr = end

    table = Table(title="Utilization & PTO Heatmap", header_style="bold magenta")
    table.add_column("Code", style="bold yellow"); table.add_column("Name", style="cyan")
    for b in buckets: table.add_column(b["l"], justify="center")

    for email, p in people.items():
        if not p.get("is_active", True): continue
        row = [p.get("short_code", "??"), p["name"]]
        for b in buckets:
            if p.get("exit_date") and b["s"] > p["exit_date"]:
                row.append("[dim]LEFT[/]"); continue

            util = calculate_utilization_at_date(email, b["s"], people, projects, allocs)
            color = get_utilization_color(util)
            util_disp = f"[{color}]{util:.0f}%[/]" if util > 0 else "[dim]0%[/]"

            has_leave = any(l['start_date'] < b['e'] and l['end_date'] >= b['s'] for l in p.get('unavailability', []))
            if has_leave:
                row.append(f"{util_disp}, [bold cyan]PTO[/bold cyan]")
            else:
                row.append(util_disp if util > 0 else "[dim].[/]")
        table.add_row(*row)
    console.print(table)

@report_app.command(name="summary")
def report_summary(
    interval: str = typer.Option("week", "--interval", "-i"),
    periods: int = typer.Option(4, "--periods", "-p")
):
    """Project-centric summary showing resource breakdowns by short-code."""
    people, projects, allocs = load_state(PEOPLE_FILE), load_state(PROJECTS_FILE), load_state(ALLOCATIONS_FILE)

    buckets = []
    curr = datetime.now().date()
    for _ in range(periods):
        start = curr
        if interval == "day": end = curr + timedelta(days=1); label = start.strftime('%m/%d')
        elif interval == "week": end = curr + timedelta(days=7); label = f"W{start.strftime('%m/%d')}"
        else: end = (curr.replace(day=28) + timedelta(days=4)).replace(day=1); label = start.strftime('%b %y')
        buckets.append({"l": label, "s": start.isoformat(), "e": end.isoformat()}); curr = end

    table = Table(title="Project Allocation Summary", header_style="bold magenta")
    table.add_column("S-Code", style="bold yellow"); table.add_column("Project", style="cyan")
    table.add_column("Lead", style="yellow")
    for b in buckets: table.add_column(b["l"], justify="center")

    for pid, pdata in projects.items():
        if pdata.get("status") == "Deleted": continue
        p_allocs = [a for a in allocs.values() if a.get('project_id') == pid]

        # Derive Lead
        lead = "N/A"
        for a in p_allocs:
            if a.get('is_lead'):
                lead = people.get(a['email'], {}).get("short_code", "???"); break

        row = [pdata.get("short_code", "??"), pdata['name'], lead]
        for b in buckets:
            bucket_res = {}
            for a in p_allocs:
                if a['start_date'] < b['e'] and a.get('end_date', '9999-12-31') >= b['s']:
                    p_info = people.get(a['email'], {})
                    code = p_info.get("short_code", "??")
                    bucket_res[code] = bucket_res.get(code, 0) + a['hours']

            if bucket_res:
                items = [f"{c}:{h}h" for c, h in sorted(bucket_res.items())]
                row.append("\n".join(items) + f"\n[dim]--[/]\n[bold]Tot:{sum(bucket_res.values())}h[/]")
            else:
                row.append("[dim].[/]")
        table.add_row(*row)
        table.add_section()
    console.print(table)

@report_app.command(name="timeoff")
def report_timeoff():
    """Comprehensive list of all logged leave across the team."""
    people = load_state(PEOPLE_FILE)
    table = Table(title="Roster Unavailability Log", header_style="bold magenta")
    table.add_column("Code", style="bold yellow"); table.add_column("Name"); table.add_column("Start"); table.add_column("End"); table.add_column("Reason")
    found = False
    for data in people.values():
        for entry in data.get("unavailability", []):
            table.add_row(data.get("short_code", "??"), data["name"], entry["start_date"], entry["end_date"], entry.get("reason", "PTO"))
            found = True
    if found: console.print(table)
    else: console.print("[yellow]No unavailability has been logged.[/yellow]")

@report_app.command(name="skills")
def report_skill_gap():
    """Compares pipeline demand against roster capabilities to identify hiring gaps."""
    projects, people = load_state(PROJECTS_FILE), load_state(PEOPLE_FILE)
    reqs, avails = {}, {}
    for p in projects.values():
        if p.get("status") in ["Active", "Proposed"]:
            for s in p.get("required_skills", []):
                n, l = s.split(":"); reqs[n] = max(reqs.get(n, 0), int(l))
    for p in people.values():
        if p.get("is_active", True):
            for s in p.get("skill", []):
                n, l = s.split(":"); avails[n] = max(avails.get(n, 0), int(l))

    table = Table(title="Organizational Skill Gap Analysis", header_style="bold magenta")
    table.add_column("Skill"); table.add_column("Max Req.", justify="center"); table.add_column("Max Avail.", justify="center"); table.add_column("Status")
    for skill, rl in reqs.items():
        al = avails.get(skill, 0)
        status = "[green]✅ Covered[/]" if al >= rl else "[red]⚠️ GAP[/]"
        table.add_row(skill, str(rl), str(al), status)
    console.print(table)

if __name__ == "__main__":
    app()
