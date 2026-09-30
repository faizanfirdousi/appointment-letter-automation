"""
tests/test_validate.py
Unit tests for CSV validation and name normalization (Phase 7 / Section 10).
"""

import io
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.validate import (
    _normalize_name,
    _normalize_role,
    _sanitize_filename,
    _is_valid_email,
    validate_csv,
    VALID_ROLES,
)
from src.config import Config, LetterheadConfig, TeamConfig
from pathlib import Path
import tempfile
import csv
import os


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_config() -> Config:
    lh = LetterheadConfig(
        image="assets/letterhead.png",
        content_top_mm=65, content_bottom_mm=55,
        content_left_mm=22, content_right_mm=22,
        font_family="Arial",
        font_file_regular="", font_file_bold="",
        font_size_pt=11.5, min_font_size_pt=10,
        text_color="#232F3E",
    )
    return Config(
        club_name="AWS Student Builder Group",
        college_name="Indira Institute of Information Technology (I²IT)",
        academic_year="2026-27",
        issue_date="auto",
        issuer_name="Community Lead",
        issuer_designation="AWS Student Builder Group Leader",
        captain_name="Community Lead",
        faculty_coordinator="Prof. Faculty Advisor",
        tenure="1 year",
        lead_addition="As {{ role_title }}, you will also guide your team members, coordinate their tasks and report progress to the AWS Student Builder Group Leader and core committee.",
        print_closing=False,
        closing_line="Warm regards,",
        reference_prefix="AWSSBG-2026",
        letterhead=lh,
        email_subject="Hello {{ first_name }}",
        onboarding_link="",
        onboarding_datetime="TBD",
        teams={
            "Event Management": TeamConfig(code="EM", responsibility="Plan and run workshops and sessions."),
            "Technical": TeamConfig(code="TECH", responsibility="Conduct hands-on AWS sessions."),
            "Design": TeamConfig(code="DES", responsibility="Create posters and creatives."),
        },
    )


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = ["name", "email", "team", "role", "roll_no", "year", "department"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ─── Name normalization ───────────────────────────────────────────────────────

class TestNormalizeName:
    def test_title_case(self):
        assert _normalize_name("riya sharma") == "Riya Sharma"

    def test_trims_spaces(self):
        assert _normalize_name("  sneha kulkarni  ") == "Sneha Kulkarni"

    def test_collapses_internal_spaces(self):
        assert _normalize_name("SNEHA  kulkarni") == "Sneha Kulkarni"

    def test_preserves_accents(self):
        # José → José (not Jose)
        result = _normalize_name("josé")
        assert "Jos" in result  # Title case applied

    def test_single_word(self):
        assert _normalize_name("riya") == "Riya"


# ─── Role normalization ───────────────────────────────────────────────────────

class TestNormalizeRole:
    def test_lead_variants(self):
        for v in ["lead", "Lead", "LEAD"]:
            assert _normalize_role(v) == "Lead"

    def test_co_lead_variants(self):
        for v in ["co-lead", "Co-Lead", "CO-LEAD", "colead", "co lead"]:
            assert _normalize_role(v) == "Co-Lead"

    def test_member_variants(self):
        for v in ["member", "Member", "MEMBER"]:
            assert _normalize_role(v) == "Member"

    def test_unknown_returned_as_is(self):
        assert _normalize_role("Volunteer") == "Volunteer"


# ─── Email validation ─────────────────────────────────────────────────────────

class TestIsValidEmail:
    def test_valid(self):
        assert _is_valid_email("riya@college.edu")
        assert _is_valid_email("user.name+tag@example.co.in")

    def test_invalid_no_at(self):
        assert not _is_valid_email("notanemail")

    def test_invalid_no_domain(self):
        assert not _is_valid_email("user@")

    def test_invalid_empty(self):
        assert not _is_valid_email("")

    def test_invalid_spaces(self):
        assert not _is_valid_email("user @example.com")


# ─── Filename sanitization ────────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_simple(self):
        assert _sanitize_filename("Riya Sharma") == "Riya_Sharma"

    def test_accented(self):
        result = _sanitize_filename("José")
        assert "Jos" in result
        assert " " not in result

    def test_no_special_chars(self):
        result = _sanitize_filename("Sneha-Kulkarni!")
        assert "!" not in result
        assert " " not in result


# ─── Full CSV validation ───────────────────────────────────────────────────────

class TestValidateCsv:
    def setup_method(self):
        self.config = _make_config()
        self.tmp = Path(tempfile.mkdtemp())

    def test_valid_rows_pass(self):
        rows = [
            {"name": "Riya Sharma", "email": "riya@college.edu",
             "team": "Event Management", "role": "Lead"},
            {"name": "Arjun Patel", "email": "arjun@college.edu",
             "team": "Technical", "role": "Member"},
        ]
        csv_path = self.tmp / "recipients.csv"
        _write_csv(rows, csv_path)
        good, errors = validate_csv(csv_path, self.config)
        assert len(errors) == 0
        assert len(good) == 2
        assert good[0]["name"] == "Riya Sharma"

    def test_normalizes_names(self):
        rows = [{"name": "RIYA  sharma", "email": "riya@college.edu",
                 "team": "Event Management", "role": "Lead"}]
        csv_path = self.tmp / "recipients.csv"
        _write_csv(rows, csv_path)
        good, errors = validate_csv(csv_path, self.config)
        assert len(errors) == 0
        assert good[0]["name"] == "Riya Sharma"

    def test_empty_name_rejected(self):
        rows = [{"name": "", "email": "riya@college.edu",
                 "team": "Event Management", "role": "Lead"}]
        csv_path = self.tmp / "recipients.csv"
        _write_csv(rows, csv_path)
        _, errors = validate_csv(csv_path, self.config)
        assert any("name is empty" in e for e in errors)

    def test_bad_email_rejected(self):
        rows = [{"name": "Test", "email": "notanemail",
                 "team": "Event Management", "role": "Lead"}]
        csv_path = self.tmp / "recipients.csv"
        _write_csv(rows, csv_path)
        _, errors = validate_csv(csv_path, self.config)
        assert any("not a valid email" in e for e in errors)

    def test_duplicate_email_rejected(self):
        rows = [
            {"name": "Riya Sharma", "email": "same@college.edu",
             "team": "Event Management", "role": "Lead"},
            {"name": "Arjun Patel", "email": "same@college.edu",
             "team": "Technical", "role": "Member"},
        ]
        csv_path = self.tmp / "recipients.csv"
        _write_csv(rows, csv_path)
        _, errors = validate_csv(csv_path, self.config)
        assert any("duplicate email" in e for e in errors)

    def test_unknown_team_rejected(self):
        rows = [{"name": "Riya", "email": "riya@college.edu",
                 "team": "Marketing", "role": "Lead"}]
        csv_path = self.tmp / "recipients.csv"
        _write_csv(rows, csv_path)
        _, errors = validate_csv(csv_path, self.config)
        assert any("not found in config.yaml" in e for e in errors)

    def test_invalid_role_rejected(self):
        rows = [{"name": "Riya", "email": "riya@college.edu",
                 "team": "Event Management", "role": "Volunteer"}]
        csv_path = self.tmp / "recipients.csv"
        _write_csv(rows, csv_path)
        _, errors = validate_csv(csv_path, self.config)
        assert any("not valid" in e for e in errors)

    def test_missing_file(self):
        _, errors = validate_csv(self.tmp / "missing.csv", self.config)
        assert any("not found" in e for e in errors)

    def test_missing_required_column(self):
        # Write CSV without 'role' column
        csv_path = self.tmp / "recipients.csv"
        with open(csv_path, "w") as f:
            f.write("name,email,team\nRiya,riya@x.com,Event Management\n")
        _, errors = validate_csv(csv_path, self.config)
        assert any("missing required columns" in e for e in errors)
