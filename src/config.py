"""
src/config.py
Loads config/config.yaml (non-secret) and .env (secrets).
Exposes a single Config dataclass used by the rest of the app.
"""

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import yaml
from dotenv import load_dotenv

# Project root is two levels above this file: src/config.py -> src/ -> root
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    """Load .env from project root (silently OK if missing)."""
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path=env_path)


@dataclass
class TeamConfig:
    code: str           # used in reference ID, e.g. "EM"
    responsibility: str # role-specific paragraph printed in the letter


@dataclass
class LetterheadConfig:
    image: str
    content_top_mm: float
    content_bottom_mm: float
    content_left_mm: float
    content_right_mm: float
    font_family: str
    font_file_regular: str
    font_file_bold: str
    font_size_pt: float
    min_font_size_pt: float
    text_color: str


@dataclass
class Config:
    # --- Non-secret (from config.yaml) ---
    club_name: str
    college_name: str
    academic_year: str
    issue_date: str          # "auto" or literal date string
    issuer_name: str
    issuer_designation: str
    captain_name: str
    faculty_coordinator: str
    tenure: str
    lead_addition: str       # Jinja2 string rendered with role_title
    print_closing: bool
    closing_line: str
    reference_prefix: str
    letterhead: LetterheadConfig
    email_subject: str
    onboarding_link: str
    onboarding_datetime: str
    teams: Dict[str, TeamConfig]   # e.g. {"Event Management": TeamConfig(...)}
    team_list_pdf: str = "aws_team_list - Team List.pdf"
    merch_form_link: str = ""

    # --- Secrets (from .env) ---
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_app_password: str = ""
    from_name: str = ""

    # --- Derived ---
    project_root: Path = field(default_factory=lambda: PROJECT_ROOT)

    def resolved_issue_date(self) -> str:
        """Return the issue date string to print on letters."""
        if self.issue_date.strip().lower() == "auto":
            return date.today().strftime("%-d %B %Y")   # e.g. "30 September 2026"
        return self.issue_date

    def abs_asset(self, relative_path: str) -> Path:
        """Resolve an asset path that is relative to the project root."""
        return self.project_root / relative_path

    def team_code(self, team_name: str) -> str:
        """Return the short code for a team name, e.g. 'Event Management' -> 'EM'."""
        tc = self.teams.get(team_name)
        return tc.code if tc else "XX"


def load_config(config_path: Optional[Path] = None) -> "Config":
    """
    Load and return the Config object.
    Reads config/config.yaml and the .env file.
    """
    _load_env()

    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Copy config/config.yaml.example to config/config.yaml and fill it in."
        )

    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    # Build LetterheadConfig
    lh_raw = raw.get("letterhead", {})
    letterhead = LetterheadConfig(
        image=lh_raw.get("image", "assets/letterhead.png"),
        content_top_mm=float(lh_raw.get("content_top_mm", 65)),
        content_bottom_mm=float(lh_raw.get("content_bottom_mm", 55)),
        content_left_mm=float(lh_raw.get("content_left_mm", 22)),
        content_right_mm=float(lh_raw.get("content_right_mm", 22)),
        font_family=lh_raw.get("font_family", "Arial"),
        font_file_regular=lh_raw.get("font_file_regular", ""),
        font_file_bold=lh_raw.get("font_file_bold", ""),
        font_size_pt=float(lh_raw.get("font_size_pt", 11.5)),
        min_font_size_pt=float(lh_raw.get("min_font_size_pt", 10)),
        text_color=lh_raw.get("text_color", "#232F3E"),
    )

    # Build teams dict: supports both old format {"Team": "CODE"} and new {"Team": {code, responsibility}}
    raw_teams = raw.get("teams", {})
    teams: Dict[str, TeamConfig] = {}
    for team_name, team_val in raw_teams.items():
        if isinstance(team_val, dict):
            teams[team_name] = TeamConfig(
                code=str(team_val.get("code", "XX")),
                responsibility=str(team_val.get("responsibility", "")),
            )
        else:
            # Legacy: just a code string
            teams[team_name] = TeamConfig(code=str(team_val), responsibility="")

    return Config(
        club_name=raw["club_name"],
        college_name=raw["college_name"],
        academic_year=raw["academic_year"],
        issue_date=str(raw.get("issue_date", "auto")),
        issuer_name=raw.get("issuer_name", raw.get("captain_name", "")),
        issuer_designation=raw.get("issuer_designation", "Club Captain"),
        captain_name=raw.get("captain_name", raw.get("issuer_name", "")),
        faculty_coordinator=raw.get("faculty_coordinator", ""),
        tenure=str(raw.get("tenure", "1 year")),
        lead_addition=str(raw.get("lead_addition", "")),
        print_closing=bool(raw.get("print_closing", False)),
        closing_line=str(raw.get("closing_line", "Warm regards,")),
        reference_prefix=raw["reference_prefix"],
        letterhead=letterhead,
        email_subject=raw.get("email_subject", "You're selected!"),
        onboarding_link=raw.get("onboarding_link", ""),
        onboarding_datetime=raw.get("onboarding_datetime", "TBD"),
        teams=teams,
        team_list_pdf=str(raw.get("team_list_pdf", "aws_team_list - Team List.pdf")),
        merch_form_link=str(raw.get("merch_form_link", "")),
        # Secrets from environment
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "587").strip()),
        smtp_user=os.getenv("SMTP_USER", "").strip(),
        smtp_app_password=os.getenv("SMTP_APP_PASSWORD", "").replace(" ", "").strip(),
        from_name=os.getenv("FROM_NAME", "").strip(),
        project_root=PROJECT_ROOT,
    )
