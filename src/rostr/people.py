import typer
from typing import Optional
from datetime import datetime
from rich.table import Table
from .config import load_config

from .ledger import append_event, load_state, PEOPLE_FILE
from .utils import console, calculate_dynamic_experience, generate_short_code, prompt_for_date

people_app = typer.Typer(help="Manage consultants, skills, and availability")

@people_app.command(name="add")
def add_person():
    cfg = load_config()
    people = load_state(PEOPLE_FILE)
    email = typer.prompt("Enter email address")
    if email in people and people[email].get("is_active", True):
        typer.secho(f"❌ Error: {email} is already active in the roster!", fg="red", bold=True)
        raise typer.Exit(code=1)

    name = typer.prompt("Enter Full Name")
    short_code = generate_short_code(name, people)
    typer.secho(f"🤖 Auto-assigned Short Code: {short_code}", fg="cyan")

    designation = typer.prompt("Designation (e.g. Lead Engineer)")
    capacity = typer.prompt("Weekly Hours Capacity", default=cfg["default_capacity"], type=int)
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
    people = load_state(PEOPLE_FILE)
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
    people = load_state(PEOPLE_FILE)
    if not email: email = typer.prompt("Consultant email")
    if email not in people: raise typer.Exit(1)

    exit_date = prompt_for_date("Last Working Day")
    append_event("PERSON_OFFBOARDED", {"email": email, "exit_date": exit_date})
    typer.secho(f"✅ Offboarding scheduled for {exit_date}.", fg="green")

@people_app.command(name="delete")
def delete_person(email: str):
    people = load_state(PEOPLE_FILE)
    if email not in people: raise typer.Exit(1)
    if typer.confirm(f"Are you sure you want to deactivate {people[email]['name']}?"):
        append_event("PERSON_DELETED", {"email": email})
        typer.secho("✅ Deactivated successfully.", fg="green")
