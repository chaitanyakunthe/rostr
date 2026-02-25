import re
import json
from pathlib import Path
from ledger import load_state, append_event, PEOPLE_FILE

def generate_short_code(name: str, existing_people: dict) -> str:
    """
    Standard logic to generate a unique short code:
    4 chars of first name + initial of last name.
    Example: 'Chaitanya Kunthe' -> 'ChaiK'.
    """
    # Collect all codes currently in use to avoid collisions
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
        suffix = str(counter)
        code = f"{base_code}{suffix}"
        counter += 1

    return code

def backfill_short_codes():
    """
    Scans the current compiled state and appends edit events for anyone
    missing a short code or needing an update to the new naming standard.
    """
    print("🔍 Loading current roster state...")
    people = load_state(PEOPLE_FILE)

    if not people:
        print("Empty roster. Nothing to migrate.")
        return

    migrated_count = 0

    # Track the temporary state to handle internal collisions during backfill
    temp_people_state = json.loads(json.dumps(people))

    for email, data in people.items():
        name = data.get("name", "Unknown")
        current_code = data.get("short_code")

        # Determine if they need a new code (if empty or we want to force the new pattern)
        # Note: If you want to keep existing manual codes, check 'if not current_code'
        new_code = generate_short_code(name, temp_people_state)

        if current_code != new_code:
            print(f"✨ Migrating {name}: {current_code} -> {new_code}")

            # Update temporary state for collision detection
            temp_people_state[email]["short_code"] = new_code

            # Append the change to the ledger
            payload = {
                "email": email,
                "short_code": new_code
            }
            append_event("PERSON_EDITED", payload)
            migrated_count += 1

    if migrated_count > 0:
        print(f"\n✅ Success! Migration complete.")
        print(f"Updated short codes for {migrated_count} consultants.")
    else:
        print("\n🙌 All consultants already match the naming standard.")

if __name__ == "__main__":
    backfill_short_codes()
