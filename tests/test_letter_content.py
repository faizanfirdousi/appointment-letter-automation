"""
tests/test_letter_content.py
Tests verifying letter content updates (letter-content-update.md §7 acceptance criteria).
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config, LetterheadConfig, TeamConfig
from src.pdf_gen import build_template_context, _render_html
from src.validate import validate_csv, validate_config
import tempfile
import csv


def _make_test_config(**overrides) -> Config:
    lh = LetterheadConfig(
        image="assets/letterhead.png",
        content_top_mm=65,
        content_bottom_mm=55,
        content_left_mm=22,
        content_right_mm=22,
        font_family="Arial",
        font_file_regular="",
        font_file_bold="",
        font_size_pt=11.5,
        min_font_size_pt=10,
        text_color="#232F3E",
    )
    defaults = dict(
        club_name="AWS Student Builder Group",
        college_name="Indira Institute of Information Technology (I²IT)",
        academic_year="2026-27",
        issue_date="30 September 2026",
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
        email_subject="Congratulations {{ first_name }}!",
        onboarding_link="",
        onboarding_datetime="TBD",
        teams={
            "Technical Writing": TeamConfig(
                code="TW",
                responsibility="As part of the Technical Writing Team, your primary responsibility will be to create content related to AWS.",
            ),
            "Event Management": TeamConfig(
                code="EM",
                responsibility="As part of the Event Management Team, you will plan and run the club's workshops.",
            ),
            "Technical": TeamConfig(
                code="TECH",
                responsibility="As part of the Technical Team, you will help conduct hands-on AWS sessions.",
            ),
        },
    )
    defaults.update(overrides)
    return Config(**defaults)


class TestLetterContentAcceptanceCriteria:
    def setup_method(self):
        self.config = _make_test_config()
        self.template_dir = Path(__file__).resolve().parent.parent / "templates"

    def test_member_gets_responsibility_and_no_lead_paragraph(self):
        """A Member in Technical Writing gets the TW paragraph and NO lead paragraph."""
        recipient = {
            "name": "Riya Sharma",
            "email": "riya@example.com",
            "team": "Technical Writing",
            "role": "Member",
            "ref_id": "AWSSBG-2026-TW-001",
        }
        html = _render_html(self.template_dir, recipient, self.config, font_size_pt=11.5)
        
        # Must contain role wording "a member of"
        assert "a member of" in html
        assert "Technical Writing Team" in html
        # Must contain TW responsibility
        assert "As part of the Technical Writing Team, your primary responsibility will be to create content related to AWS." in html
        # Must NOT contain lead paragraph
        assert "guide your team members" not in html
        assert "As Team Lead" not in html

    def test_lead_gets_responsibility_and_lead_paragraph(self):
        """A Lead in Event Management gets the EM paragraph and lead paragraph with proper role phrase."""
        recipient = {
            "name": "Alex Johnson",
            "email": "alex@example.com",
            "team": "Event Management",
            "role": "Lead",
            "ref_id": "AWSSBG-2026-EM-001",
        }
        html = _render_html(self.template_dir, recipient, self.config, font_size_pt=11.5)

        # First sentence has role_phrase
        assert "the Team Lead of" in html
        assert "Event Management Team" in html
        # Has lead addition
        assert "As Team Lead, you will also guide your team members" in html
        # Has EM responsibility
        assert "As part of the Event Management Team, you will plan and run" in html

    def test_changing_team_responsibility_in_config_changes_letter(self):
        """Changing a team's responsibility in config changes the letter."""
        custom_resp = "Custom responsibility paragraph for testing dynamic config."
        cfg = _make_test_config(
            teams={
                "Technical Writing": TeamConfig(code="TW", responsibility=custom_resp),
            }
        )
        recipient = {
            "name": "Test Person",
            "email": "test@example.com",
            "team": "Technical Writing",
            "role": "Member",
            "ref_id": "AWSSBG-2026-TW-001",
        }
        html = _render_html(self.template_dir, recipient, cfg, font_size_pt=11.5)
        assert custom_resp in html

    def test_changing_people_and_tenure_in_config_changes_letter(self):
        """Changing captain_name, faculty_coordinator, or tenure changes the letter."""
        cfg = _make_test_config(
            captain_name="Jane Doe",
            faculty_coordinator="Dr. John Smith",
            tenure="2 years",
        )
        recipient = {
            "name": "Test Person",
            "email": "test@example.com",
            "team": "Technical",
            "role": "Member",
            "ref_id": "AWSSBG-2026-TECH-001",
        }
        html = _render_html(self.template_dir, recipient, cfg, font_size_pt=11.5)
        assert "Jane Doe" in html
        assert "Dr. John Smith" in html
        assert "2 years" in html

    def test_closing_not_printed_when_print_closing_false(self):
        """Closing line is omitted when print_closing is false (since it's in letterhead)."""
        recipient = {
            "name": "Test Person",
            "email": "test@example.com",
            "team": "Technical",
            "role": "Member",
            "ref_id": "AWSSBG-2026-TECH-001",
        }
        html = _render_html(self.template_dir, recipient, self.config, font_size_pt=11.5)
        assert "Warm regards," not in html

    def test_closing_printed_when_print_closing_true(self):
        """Closing line is printed when print_closing is true."""
        cfg = _make_test_config(print_closing=True, closing_line="Sincerely,")
        recipient = {
            "name": "Test Person",
            "email": "test@example.com",
            "team": "Technical",
            "role": "Member",
            "ref_id": "AWSSBG-2026-TECH-001",
        }
        html = _render_html(self.template_dir, recipient, cfg, font_size_pt=11.5)
        assert "Sincerely," in html
        assert "AWS Student Builder Group" in html

    def test_unknown_team_in_csv_fails_validation(self):
        """Unknown team stops run with clear error."""
        tmp = Path(tempfile.mkdtemp())
        csv_path = tmp / "test.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "email", "team", "role"])
            writer.writerow(["Riya", "riya@test.com", "Unknown Team", "Lead"])

        _, errors = validate_csv(csv_path, self.config)
        assert any('team "Unknown Team" not found in config.yaml' in e for e in errors)

    def test_config_validation_missing_fields(self):
        """Missing required config fields fail config validation."""
        cfg = _make_test_config(faculty_coordinator="")
        errors = validate_config(cfg)
        assert any("faculty_coordinator" in e for e in errors)
