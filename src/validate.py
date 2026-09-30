"""
src/validate.py
Validates and normalises rows from data/recipients.csv.
Returns a list of clean dicts (good rows) and prints a detailed error report.
"""

import re
import unicodedata
from pathlib import Path
from typing import List, Tuple, Dict, Any

import pandas as pd

from src.config import Config

# Allowed role values (canonical forms)
VALID_ROLES = {"Lead", "Co-Lead", "Member"}

# Required CSV columns
REQUIRED_COLUMNS = ["name", "email", "team", "role"]

# Optional columns
OPTIONAL_COLUMNS = ["roll_no", "year", "department"]


def _normalize_name(raw: str) -> str:
    """Normalize a person's name: strip, collapse spaces, Title Case."""
    stripped = " ".join(raw.strip().split())
    return stripped.title()


def _normalize_role(raw: str) -> str:
    """Map any case variant of a role to its canonical form."""
    mapping = {
        "lead":     "Lead",
        "co-lead":  "Co-Lead",
        "colead":   "Co-Lead",
        "co lead":  "Co-Lead",
        "member":   "Member",
    }
    return mapping.get(raw.strip().lower(), raw.strip())


def _is_valid_email(email: str) -> bool:
    """Simple RFC-ish email validation."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def _sanitize_filename(name: str) -> str:
    """Convert 'Riya Sharma' -> 'Riya_Sharma', stripping accents."""
    normalized = unicodedata.normalize("NFD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^\w]", "_", ascii_name)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe


def _closest_team(name: str, valid_teams: set) -> str:
    """Return a suggestion for a mistyped team name (simple substring match)."""
    name_lower = name.lower()
    for t in sorted(valid_teams):
        if name_lower in t.lower() or t.lower() in name_lower:
            return t
    return ""


def validate_config(config: Config) -> List[str]:
    """
    Validate the config itself: required top-level keys and team entries.
    Returns a list of error strings (empty = OK).
    """
    errors = []
    for field in ["club_name", "captain_name", "faculty_coordinator", "tenure"]:
        val = getattr(config, field, "")
        if not val or not str(val).strip():
            errors.append(f"config.yaml: '{field}' is empty or missing")

    for team_name, tc in config.teams.items():
        if not tc.code:
            errors.append(f"config.yaml: team '{team_name}' has no 'code'")
        if not tc.responsibility:
            errors.append(f"config.yaml: team '{team_name}' has no 'responsibility' text")

    return errors


def validate_csv(
    csv_path: Path, config: Config
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Read and validate the recipients CSV.

    Returns:
        (good_rows, errors)
        good_rows  - list of dicts with normalised values.
        errors     - list of human-readable error strings.
    """
    errors: List[str] = []

    # --- Config self-check first ---
    config_errors = validate_config(config)
    errors.extend(config_errors)

    # --- File existence ---
    if not csv_path.exists():
        return [], errors + [f"CSV file not found: {csv_path}"]

    # --- Load ---
    try:
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    except Exception as exc:
        return [], errors + [f"Could not read CSV: {exc}"]

    df.columns = [c.strip().lower() for c in df.columns]

    # --- Required columns check ---
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        return [], errors + [f"CSV is missing required columns: {missing_cols}"]

    good_rows: List[Dict[str, Any]] = []
    seen_emails: Dict[str, int] = {}
    valid_teams = set(config.teams.keys())

    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        row_errors: List[str] = []

        # ---- name ----
        raw_name = str(row.get("name", "")).strip()
        if not raw_name:
            row_errors.append("name is empty")
            name = ""
        else:
            name = _normalize_name(raw_name)
            if len(name) < 2:
                row_errors.append(f"name '{raw_name}' is too short")

        # ---- email ----
        raw_email = str(row.get("email", "")).strip().lower()
        if not raw_email:
            row_errors.append("email is empty")
            email = ""
        elif not _is_valid_email(raw_email):
            row_errors.append(f"email '{raw_email}' is not a valid email address")
            email = raw_email
        else:
            email = raw_email
            if email in seen_emails:
                row_errors.append(
                    f"duplicate email '{email}' (first seen on row {seen_emails[email]})"
                )
            else:
                seen_emails[email] = row_num

        # ---- team ----
        raw_team = str(row.get("team", "")).strip()
        if not raw_team:
            row_errors.append("team is empty")
            team = ""
        elif raw_team not in valid_teams:
            suggestion = _closest_team(raw_team, valid_teams)
            hint = f" Did you mean \"{suggestion}\"?" if suggestion else f" Valid teams: {sorted(valid_teams)}"
            row_errors.append(f"team \"{raw_team}\" not found in config.yaml.{hint}")
            team = raw_team
        else:
            # Ensure team has a responsibility
            tc = config.teams[raw_team]
            if not tc.responsibility:
                row_errors.append(
                    f"team '{raw_team}' has no 'responsibility' text in config.yaml"
                )
            team = raw_team

        # ---- role ----
        raw_role = str(row.get("role", "")).strip()
        role = _normalize_role(raw_role)
        if role not in VALID_ROLES:
            row_errors.append(
                f"role '{raw_role}' is not valid (must be Lead, Co-Lead, or Member)"
            )

        # ---- optional columns ----
        optional: Dict[str, str] = {}
        for col in OPTIONAL_COLUMNS:
            optional[col] = str(row.get(col, "")).strip()

        if row_errors:
            for err in row_errors:
                errors.append(
                    f"Row {row_num} ({raw_name or '(no name)'}/{raw_email or '(no email)'}): {err}"
                )
        else:
            good_rows.append(
                {
                    "name":       name,
                    "email":      email,
                    "team":       team,
                    "role":       role,
                    "roll_no":    optional.get("roll_no", ""),
                    "year":       optional.get("year", ""),
                    "department": optional.get("department", ""),
                    "safe_name":  _sanitize_filename(name),
                }
            )

    return good_rows, errors


def print_validation_report(good_rows: List[Dict], errors: List[str]) -> bool:
    """Print a clear validation report. Returns True if all rows valid."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        if errors:
            console.print(
                f"\n[bold red]✗ Validation FAILED — {len(errors)} error(s) found:[/bold red]\n"
            )
            for err in errors:
                console.print(f"  [red]• {err}[/red]")
            console.print()
        else:
            console.print(
                f"\n[bold green]✓ All {len(good_rows)} row(s) valid.[/bold green]\n"
            )

        if good_rows:
            table = Table(title="Valid recipients", show_lines=True)
            table.add_column("Name",  style="cyan")
            table.add_column("Email", style="blue")
            table.add_column("Team",  style="magenta")
            table.add_column("Role",  style="yellow")
            for r in good_rows:
                table.add_row(r["name"], r["email"], r["team"], r["role"])
            console.print(table)

    except ImportError:
        if errors:
            print(f"\n✗ Validation FAILED — {len(errors)} error(s) found:\n")
            for err in errors:
                print(f"  • {err}")
        else:
            print(f"\n✓ All {len(good_rows)} row(s) valid.\n")

    return len(errors) == 0
