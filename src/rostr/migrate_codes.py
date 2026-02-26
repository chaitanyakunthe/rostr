import re
import json
from pathlib import Path
from ledger import load_state, append_event, PEOPLE_FILE, PROJECTS_FILE

# --- REPLICATED LOGIC FROM CANVAS ---

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
    # Collision resolution
    while code.upper() in existing_codes:
        code = f"{base_code}{counter}"
        counter += 1

    return code

def generate_project_short_code(name: str, existing_projects: dict) -> str:
    """
    Generates a unique 6-8 char short code for projects.
    Logic: First 6 chars of first word + Initial of last word.
    Example: 'Internal HR Portal' -> 'InternP'.
    """
    existing_codes = {p.get("short_code", "").upper() for p in existing_projects.values() if "short_code" in p}

    parts = name.strip().split()
    if not parts:
        base_code = "PROJ"
    else:
        # First word (up to 6 chars)
        first_part = parts[0][:6].capitalize()
        # Initial of last word (Uppercase)
        last_part = parts[-1][0].upper() if len(parts) > 1 else ""
        base_code = first_part + last_part

    code = base_code
    counter = 1
    # Collision resolution
    while code.upper() in existing_codes:
        suffix = str(counter)
        code = base_code[:8-len(suffix)] + suffix
        counter += 1

    return code

# --- MIGRATION LOGIC ---

def migrate_all_codes():
    """
    Scans both People and Projects to backfill or update short codes
    to the latest standard.
    """
    # 1. MIGRATE PEOPLE
    print("👥 Checking Consultant Roster...")
    people = load_state(PEOPLE_FILE)
    migrated_people = 0
    temp_people_state = json.loads(json.dumps(people)) # Local copy for collision tracking

    for email, data in people.items():
        name = data.get("name", "Unknown")
        current_code = data.get("short_code")

        # We generate the code based on the NEW standard
        new_code = generate_short_code(name, temp_people_state)

        # If they have no code, or the code doesn't match the new standard
        if current_code != new_code:
            print(f"  ✨ Updating {name}: {current_code or 'None'} -> {new_code}")
            temp_people_state[email]["short_code"] = new_code
            append_event("PERSON_EDITED", {"email": email, "short_code": new_code})
            migrated_people += 1

    # 2. MIGRATE PROJECTS
    print("\n🏗️  Checking Project List...")
    projects = load_state(PROJECTS_FILE)
    migrated_projects = 0
    temp_projects_state = json.loads(json.dumps(projects))

    for pid, data in projects.items():
        name = data.get("name", "Unknown Project")
        current_code = data.get("short_code")

        new_code = generate_project_short_code(name, temp_projects_state)

        if current_code != new_code:
            print(f"  ✨ Updating Project '{name}': {current_code or 'None'} -> {new_code}")
            temp_projects_state[pid]["short_code"] = new_code
            append_event("PROJECT_EDITED", {"project_id": pid, "short_code": new_code})
            migrated_projects += 1

    print("\n--- Migration Summary ---")
    print(f"Consultants updated: {migrated_people}")
    print(f"Projects updated:    {migrated_projects}")
    if migrated_people + migrated_projects > 0:
        print("✅ The ledger has been updated and state files rebuilt.")
    else:
        print("🙌 All entries already match the current standards.")

if __name__ == "__main__":
    migrate_all_codes()
