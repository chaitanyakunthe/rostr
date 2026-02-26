import typer
from datetime import datetime, timedelta
from rich.table import Table

from .config import load_config
from .ledger import load_state, PEOPLE_FILE, PROJECTS_FILE, ALLOCATIONS_FILE
from .utils import console, get_utilization_color, calculate_utilization_at_date

report_app = typer.Typer(help="Generate utilization, forecast, and gap reports")

@report_app.command(name="current")
def report_current():
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
def report_forecast(months: int = typer.Option(None, "--months", "-m")):
    cfg = load_config()
    months = months or cfg["forecast_months"]
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
