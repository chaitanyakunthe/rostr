# rostr

[![PyPI version](https://img.shields.io/pypi/v/rostr.svg)](https://pypi.org/project/rostr/)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Rostr** is a fast, text-based CLI tool for managing a team's capacity, skills, and project allocations. 

Built with an **Event-Sourced architecture**, Rostr doesn't just store your current state—it maintains an immutable ledger of every staffing change you make. It provides instant, beautifully formatted terminal dashboards to help you forecast utilization, spot bottlenecks, and manage your pipeline.

## 🔥 What's New in v0.2.0
* **Interactive Setup Wizard:** Run `rostr setup` to personalize your workspace globally.
* **Custom Date Formats:** Input and view dates your way—choose between `YYYY-MM-DD` (ISO), `DD/MM/YYYY` (EU/India), or `MM/DD/YYYY` (US).
* **Workspace Defaults:** Set your region's default weekly capacity and custom forecast horizons.
* **Smart Shortcodes:** Customize the auto-generated length of your team and project shortcodes to fit your organization's naming conventions.
* **Modular Architecture:** Under-the-hood rewrite separating `people`, `project`, and `report` modules for faster execution and better scalability.


## ✨ Key Features
* **Terminal-Native Dashboards:** Rich, color-coded heatmaps and matrix reports right in your terminal.
* **Event-Sourced Ledger:** Every addition, allocation, and time-off request is stored as an immutable event.
* **Smart Forecasting:** View utilization projections across days, weeks, or months.
* **Pipeline vs. Active Tracking:** Filter utilization by 100% confirmed work vs. probable pipeline work.
* **Context-Aware Availability:** Automatically accounts for PTO and Last Working Days (LWD).

---

## 🚀 Installation

Rostr is a globally available CLI tool. The recommended way to install it is using `pipx`, which keeps the tool and its dependencies safely isolated from your system Python.

### Option 1: Install via pipx (**Recommended**)

```bash
pipx install rostr
```

### Option 2: Install via pip

```bash
pip install rostr
```

### Option 3: Install from Source (**For Development**)

Clone the repository and install the dependencies using Poetry:

```bash
git clone [https://github.com/chaitanyakunthe/rostr.git](https://github.com/chaitanyakunthe/rostr.git)
cd rostr
poetry install
```
---
## 📖 Quick Start Guide

Once installed, you can access the tool from anywhere on your computer simply by typing `rostr`.
Here is the basic workflow to get your first report running.

### 0. Setup

On your very first run, Rostr will automatically launch a setup wizard. You can also trigger this manually at any time to change your date formats, default hours, and reporting targets.

```bash
rostr setup
```
If you ever get stuck, `rostr --help` will help you. For command specific help - `rostr <command> --help` and so on.

### 1. Build your team

Add people to your roster and define their weekly capacity (default is 40 hours).

```bash
rostr people add
rostr people list
```

### 2. Log timeoffs and exits

Ensure your forecasts are accurate by changes and plotting timeoffs.

```bash
rostr people edit
rostr people timeoff
```

Remove people from your roster.

```bash
rostr people offboard
rostr people delete
```

### 3. Create Projects

Add projects to your pipeline. You can mark them as `Active`, `Proposed`, etc., and assign a win probability.

```bash
rostr project add
rostr project list
```

### 4. Allocate People to Projects and remove them

Assign your team to projects with start and end dates.

```bash
rostr project allocate
rostr project unallocate
```

## 📊 Reporting & Dashboards

Rostr's true power lies in its reporting engine.

#### Current Utilization
See exactly what your team is working on today, broken down by project.

```bash
rostr report current
```

#### Timeline Heatmap
View a color-coded matrix of when people are freeing up across days, weeks, or months.

```bash
rostr report timeline --interval week --periods 4
```

#### Pipeline Forecast
Look months into the future. See utilization percentages weighted by project probability.

```bash
# View the next 3 months (Default)
rostr report forecast --months 3
# Filter to see ONLY confirmed/active work
rostr report forecast --view active
# Filter to see ONLY proposed/pipeline work
rostr report forecast --view probable
```

#### Know how is not available
Generate a timeoff report to know unavailable dates

```bash
rostr report timeoff
```

#### Know your gaps in skill

```bash
rostr report skills
```

## 🗄️ Where is my data stored?

Rostr uses a local, privacy-first storage model. No databases to spin up, and no cloud servers. All your data is saved locally on your machine in your home directory:
- Path: `~/.rostr/`
- Files: You will find `rostr_journal.jsonl` (your event ledger) and several derived state files (`rostr_people.json`, etc.)

> If you ever want to back up your roster or share it with a colleague, simply copy the `~/.rostr/rostr_journal.jsonl`  file!

### ⚠️ CRITICAL WARNING: THE EVENT JOURNAL
Rostr relies on an **Event-Sourced Architecture**. This means the `rostr_journal.jsonl` file is the absolute brain and single source of truth for your entire application. 

* **✅ SAFE TO DELETE:** `rostr_people.json`, `rostr_projects.json`, and `rostr_allocations.json`. If you delete these, Rostr will automatically and perfectly rebuild them from the journal the next time you run a command.
* **❌ DO NOT DELETE:** `rostr_journal.jsonl`. If you delete or manually corrupt this file, **all of your data will be permanently wiped out** the next time you add a person or project. 

**Backups:** Because of this architecture, `rostr_journal.jsonl` is the *only* file you need to back up. If you move to a new computer, just install Rostr, drop your old journal file into the `~/.rostr/` folder, and the app will instantly rebuild your entire workspace.

## 🤝 Contributing

Contributions are welcome! If you have ideas for new reports, commands, or features:

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request.

**License:** MIT
