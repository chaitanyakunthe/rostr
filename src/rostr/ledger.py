import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# --- FILE SETUP ---
# Save data to the user's home directory so it's globally accessible and safe
DATA_DIR = Path.home() / ".rostr"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Define our file paths
JOURNAL_FILE = DATA_DIR / "rostr_journal.jsonl"
PEOPLE_FILE = DATA_DIR / "rostr_people.json"
PROJECTS_FILE = DATA_DIR / "rostr_projects.json"
ALLOCATIONS_FILE = DATA_DIR / "rostr_allocations.json"

# --- THE WRITER (Append-Only) ---
def append_event(event_type: str, payload: dict):
    """
    Appends a new event to the immutable ledger and immediately rebuilds the state.
    """
    event = {
        "event_id": str(uuid.uuid4()), # Unique ID for every action
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": payload
    }

    # Write to the journal in append mode ('a')
    with JOURNAL_FILE.open("a") as f:
        f.write(json.dumps(event) + "\n")

    # Trigger the reducer to update the state files
    rebuild_state()


# --- THE REDUCER (Rebuilds current reality) ---
def rebuild_state():
    """
    Reads the entire journal from top to bottom and compiles the current state
    of people, projects, and allocations, then saves them to fast-read JSON files.
    """
    # Start with a blank slate
    state_people = {}
    state_projects = {}
    state_allocations = {}

    # If no journal exists yet, just save the empty states and return
    if not JOURNAL_FILE.exists():
        _save_state(PEOPLE_FILE, state_people)
        _save_state(PROJECTS_FILE, state_projects)
        _save_state(ALLOCATIONS_FILE, state_allocations)
        return

    # Read history chronologically
    with JOURNAL_FILE.open("r") as f:
        for line in f:
            if not line.strip():
                continue # Skip empty lines

            event = json.loads(line)
            e_type = event["event_type"]
            data = event["payload"]

            # --- APPLY PEOPLE EVENTS ---
            if e_type == "PERSON_ADDED":
                state_people[data["email"]] = data
            elif e_type == "PERSON_EDITED":
                if data["email"] in state_people:
                    state_people[data["email"]].update(data)
            elif e_type == "PERSON_DELETED":
                if data["email"] in state_people:
                    state_people[data["email"]]["is_active"] = False # We deactivate, not delete!
            elif e_type == "PERSON_OFFBOARDED":
                if data["email"] in state_people:
                    state_people[data["email"]]["exit_date"] = data["exit_date"]
                elif e_type == "UNAVAILABILITY_ADDED":
                    email = data["email"]
                    if email in state_people:
                        if "unavailability" not in state_people[email]:
                            state_people[email]["unavailability"] = []
                        state_people[email]["unavailability"].append({
                            "start_date": data["start_date"],
                            "end_date": data["end_date"],
                            "reason": data.get("reason", "PTO")
                        })

            # --- APPLY PROJECT EVENTS ---
            elif e_type == "PROJECT_ADDED":
                state_projects[data["project_id"]] = data
            elif e_type == "PROJECT_EDITED":
                if data["project_id"] in state_projects:
                    state_projects[data["project_id"]].update(data)
            elif e_type == "PROJECT_DELETED":
                if data["project_id"] in state_projects:
                    state_projects[data["project_id"]]["status"] = "Deleted"

            # --- APPLY ALLOCATION EVENTS ---
            elif e_type == "ALLOCATION_ADDED":
                alloc_id = data["allocation_id"]
                state_allocations[alloc_id] = data
            elif e_type == "ALLOCATION_REMOVED":
                alloc_id = data["allocation_id"]
                if alloc_id in state_allocations:
                    del state_allocations[alloc_id]

    # Finally, save the compiled realities to our fast-read JSON files
    _save_state(PEOPLE_FILE, state_people)
    _save_state(PROJECTS_FILE, state_projects)
    _save_state(ALLOCATIONS_FILE, state_allocations)


# --- 4. HELPER FUNCTIONS ---
def _save_state(filepath: Path, data: dict):
    """Helper to save a dictionary to a JSON file cleanly."""
    with filepath.open("w") as f:
        json.dump(data, f, indent=2)

def load_state(filepath: Path) -> dict:
    """Helper for the CLI to instantly read the compiled state."""
    try:
        with filepath.open("r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
