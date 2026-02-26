import re
from typing import Optional, Dict, Any
from datetime import datetime
import typer
from rich.console import Console

# Initialize a single console to be imported across all apps
console = Console()

def calculate_dynamic_experience(stored_exp: float, update_date_str: Optional[str]) -> float:
    if not update_date_str:
        return stored_exp
    try:
        update_date = datetime.strptime(update_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        delta_days = (today - update_date).days
        years_elapsed = delta_days / 365.25
        return round(stored_exp + years_elapsed, 1)
    except (ValueError, TypeError):
        return stored_exp

def generate_short_code(name: str, existing_people: Dict[str, Any]) -> str:
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
        code = base_code[:8-len(suffix)] + suffix
        counter += 1
    return code

def generate_project_id(name: str, existing_projects: Dict[str, Any]) -> str:
    base_id = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not base_id: base_id = "project"
    project_id, counter = base_id, 1
    while project_id in existing_projects:
        counter += 1
        project_id = f"{base_id}-{counter}"
    return project_id

def prompt_for_date(prompt_text: str, allow_empty: bool = False) -> str:
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
    if utilization_pct > 100: return "red"
    if utilization_pct >= 75: return "green"
    return "yellow"

def calculate_utilization_at_date(email: str, target_date: str, people: dict, projects: dict, allocations: dict) -> float:
    person_data = people.get(email, {})
    base_capacity = person_data.get("capacity", 40)
    if base_capacity <= 0: return 0.0

    expected_hours = 0.0
    for alloc in allocations.values():
        if alloc["email"] == email:
            start, end = alloc["start_date"], alloc.get("end_date", "2099-12-31")
            if start <= target_date <= end:
                proj = projects.get(alloc["project_id"], {})
                if proj.get("status") not in ["Deleted", "Lost", "Completed"]:
                    prob = proj.get("probability", 100)
                    expected_hours += alloc["hours"] * (prob / 100.0)
    return (expected_hours / base_capacity) * 100
