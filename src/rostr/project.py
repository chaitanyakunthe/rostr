import uuid
from typing import Optional
from datetime import datetime, timedelta
import typer
from rich.table import Table

from .ledger import append_event, load_state, PROJECTS_FILE, PEOPLE_FILE, ALLOCATIONS_FILE
from .utils import console, generate_project_id, generate_project_short_code, calculate_dynamic_experience, prompt_for_date

project_app = typer.Typer(help="Manage projects and staffing allocations")

@project_app.command(name="add")
def add_project():
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
    projects = load_state(PROJECTS_FILE)
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
    projects, people = load_state(PROJECTS_FILE), load_state(PEOPLE_FILE)

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
