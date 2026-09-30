"""
tests/test_log.py
Unit tests for the send log (idempotency, ref ID, CRUD).
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import log as sendlog
from src.pdf_gen import generate_ref_id, role_title


# ─── Reference ID generation ─────────────────────────────────────────────────

class TestRefId:
    def test_format(self):
        ref = generate_ref_id("AWSCC-2026", "EM", "riya@x.com", 1)
        assert ref == "AWSCC-2026-EM-001"

    def test_counter_pads(self):
        ref = generate_ref_id("AWSCC-2026", "TECH", "a@b.com", 10)
        assert ref == "AWSCC-2026-TECH-010"

    def test_unique_for_different_teams(self):
        r1 = generate_ref_id("X", "EM", "a@b.com", 1)
        r2 = generate_ref_id("X", "TECH", "c@d.com", 1)
        assert r1 != r2


# ─── Role title ───────────────────────────────────────────────────────────────

class TestRoleTitle:
    def test_lead(self):
        assert role_title("Lead") == "Team Lead"

    def test_co_lead(self):
        assert role_title("Co-Lead") == "Team Co-Lead"

    def test_member(self):
        assert role_title("Member") == "Team Member"

    def test_unknown_passthrough(self):
        assert role_title("Volunteer") == "Volunteer"


# ─── Send log CRUD ────────────────────────────────────────────────────────────

class TestSendLog:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_empty_on_missing_file(self):
        result = sendlog.load_log(self.tmp / "nonexistent")
        assert result == {}

    def test_upsert_and_save_load(self):
        log: dict = {}
        sendlog.upsert_entry(
            log, "a@b.com",
            name="Alice", team="Technical", role="Lead",
            ref_id="X-001", status=sendlog.STATUS_PENDING,
        )
        sendlog.save_log(self.tmp, list(log.values()))
        loaded = sendlog.load_log(self.tmp)
        assert "a@b.com" in loaded
        assert loaded["a@b.com"]["status"] == sendlog.STATUS_PENDING

    def test_is_already_sent_true(self):
        log: dict = {}
        sendlog.upsert_entry(log, "a@b.com", status=sendlog.STATUS_SENT)
        assert sendlog.is_already_sent(log, "a@b.com")

    def test_is_already_sent_false(self):
        log: dict = {}
        sendlog.upsert_entry(log, "a@b.com", status=sendlog.STATUS_FAILED)
        assert not sendlog.is_already_sent(log, "a@b.com")

    def test_get_failed_emails(self):
        log: dict = {}
        sendlog.upsert_entry(log, "a@b.com", status=sendlog.STATUS_FAILED)
        sendlog.upsert_entry(log, "c@d.com", status=sendlog.STATUS_SENT)
        failed = sendlog.get_failed_emails(log)
        assert "a@b.com" in failed
        assert "c@d.com" not in failed

    def test_idempotency_no_double_sent(self):
        """Simulates re-running: SENT entry should be skippable."""
        log: dict = {}
        sendlog.upsert_entry(log, "a@b.com", status=sendlog.STATUS_SENT)
        # isAlreadySent returns True => the run loop skips this person
        assert sendlog.is_already_sent(log, "a@b.com") is True

    def test_status_overwrite(self):
        log: dict = {}
        sendlog.upsert_entry(log, "a@b.com", status=sendlog.STATUS_PENDING)
        sendlog.upsert_entry(log, "a@b.com", status=sendlog.STATUS_SENT)
        assert log["a@b.com"]["status"] == sendlog.STATUS_SENT
