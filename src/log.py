"""
src/log.py
Read/write the persistent send log at output/send_log.csv.
Statuses: PENDING | GENERATED | SENT | FAILED
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

LOG_COLUMNS = [
    "name",
    "email",
    "team",
    "role",
    "ref_id",
    "status",
    "error",
    "timestamp",
]

# Possible status values
STATUS_PENDING   = "PENDING"
STATUS_GENERATED = "GENERATED"
STATUS_SENT      = "SENT"
STATUS_FAILED    = "FAILED"


def _log_path(output_dir: Path) -> Path:
    return output_dir / "send_log.csv"


def load_log(output_dir: Path) -> Dict[str, Dict]:
    """
    Load existing log into a dict keyed by email.
    Returns {} if the log file does not exist yet.
    """
    path = _log_path(output_dir)
    if not path.exists():
        return {}

    result: Dict[str, Dict] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            result[row["email"]] = dict(row)
    return result


def save_log(output_dir: Path, entries: List[Dict]) -> None:
    """
    Write all entries back to the log file (overwrites).
    Creates the output directory if missing.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _log_path(output_dir)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(entries)


def upsert_entry(
    log: Dict[str, Dict],
    email: str,
    *,
    name: str = "",
    team: str = "",
    role: str = "",
    ref_id: str = "",
    status: str = STATUS_PENDING,
    error: str = "",
) -> None:
    """
    Insert or update a log entry in the in-memory dict.
    Pass only the fields you want to change; the rest are preserved.
    """
    existing = log.get(email, {})
    log[email] = {
        "name":      name      or existing.get("name", ""),
        "email":     email,
        "team":      team      or existing.get("team", ""),
        "role":      role      or existing.get("role", ""),
        "ref_id":    ref_id    or existing.get("ref_id", ""),
        "status":    status,
        "error":     error,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def is_already_sent(log: Dict[str, Dict], email: str) -> bool:
    """Return True if this email is already SENT in the log."""
    entry = log.get(email)
    return entry is not None and entry.get("status") == STATUS_SENT


def get_failed_emails(log: Dict[str, Dict]) -> List[str]:
    """Return list of emails whose last status was FAILED."""
    return [
        email
        for email, entry in log.items()
        if entry.get("status") == STATUS_FAILED
    ]


def print_summary(log: Dict[str, Dict]) -> None:
    """Print a summary table of the run results."""
    total     = len(log)
    generated = sum(1 for e in log.values() if e["status"] == STATUS_GENERATED)
    sent      = sum(1 for e in log.values() if e["status"] == STATUS_SENT)
    failed    = sum(1 for e in log.values() if e["status"] == STATUS_FAILED)
    pending   = sum(1 for e in log.values() if e["status"] == STATUS_PENDING)

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Run Summary", show_header=True)
        table.add_column("Status",    style="bold")
        table.add_column("Count",     justify="right")
        table.add_row("Total",        str(total))
        table.add_row("Generated",    str(generated), style="cyan")
        table.add_row("Sent",         str(sent),      style="green")
        table.add_row("Failed",       str(failed),    style="red")
        table.add_row("Pending",      str(pending),   style="yellow")
        console.print()
        console.print(table)
        if failed:
            console.print(
                f"\n[red]Re-run with [bold]--send --retry-failed[/bold] to retry {failed} failed recipient(s).[/red]\n"
            )
    except ImportError:
        print("\n--- Run Summary ---")
        print(f"  Total:     {total}")
        print(f"  Generated: {generated}")
        print(f"  Sent:      {sent}")
        print(f"  Failed:    {failed}")
        print(f"  Pending:   {pending}")
        if failed:
            print(f"\n  Re-run with --send --retry-failed to retry {failed} failed recipient(s).\n")
