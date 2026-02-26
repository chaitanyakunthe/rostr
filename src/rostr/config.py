import json
from pathlib import Path
import typer
from rich.console import Console

# We mirror the DATA_DIR from ledger.py to keep configs in the same place
DATA_DIR = Path.home() / ".rostr"
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "default_capacity": 40,
    "forecast_months": 3,
    "person_shortcode_len": 4,
    "project_shortcode_len": 6,
    "utilization_target": 75.0,
    "date_format": "%Y-%m-%d"
}

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with CONFIG_FILE.open("r") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except json.JSONDecodeError:
        return DEFAULT_CONFIG.copy()

def save_config(config_data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w") as f:
        json.dump(config_data, f, indent=2)

def run_setup_wizard():
    console = Console()
    console.print("\n[bold cyan]🛠️  Welcome to Rostr Setup![/bold cyan]")
    console.print("Let's configure your workspace preferences. You can change these anytime with 'rostr setup'.\n")

    config = load_config()

    config["default_capacity"] = typer.prompt("Default Weekly Capacity (hours)", default=config["default_capacity"], type=int)
    config["forecast_months"] = typer.prompt("Default Forecast Horizon (months)", default=config["forecast_months"], type=int)
    config["person_shortcode_len"] = typer.prompt("Person Shortcode Base Length (letters)", default=config["person_shortcode_len"], type=int)
    config["project_shortcode_len"] = typer.prompt("Project Shortcode Base Length (letters)", default=config["project_shortcode_len"], type=int)
    config["utilization_target"] = typer.prompt("Healthy Utilization Target % (e.g., 75.0 or 80.0)", default=config["utilization_target"], type=float)

    console.print("\n[bold]Date Format Preference:[/bold]")
    console.print("1: YYYY-MM-DD (ISO standard)")
    console.print("2: DD/MM/YYYY (EU/India)")
    console.print("3: MM/DD/YYYY (US)")

    # Map current config back to choice for defaults
    current_choice = "1"
    if config["date_format"] == "%d/%m/%Y": current_choice = "2"
    elif config["date_format"] == "%m/%d/%Y": current_choice = "3"

    date_choice = typer.prompt("Choose date input/display format", default=current_choice, type=str)

    if date_choice == "2": config["date_format"] = "%d/%m/%Y"
    elif date_choice == "3": config["date_format"] = "%m/%d/%Y"
    else: config["date_format"] = "%Y-%m-%d"

    save_config(config)
    console.print("\n[bold green]✅ Configuration saved successfully![/bold green]\n")
