#!/usr/bin/env python3
"""
main.py  —  Appointment Letter Automation CLI
AWS Student Builder Group

Usage examples:
  python main.py --help
  python main.py preview --guides
  python main.py validate
  python main.py run
  python main.py run --send
  python main.py run --send --test-email me@gmail.com
  python main.py run --send --retry-failed
  python main.py run --send --only riya@college.edu
  python main.py run --send --team "Event Management"
  python main.py run --force
"""

import argparse
import sys
import time
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Pretty console (rich is optional but recommended)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from rich.console import Console
    from rich.rule import Rule
    console = Console()
    def _print(msg: str, style: str = "") -> None:
        if style:
            console.print(msg, style=style)
        else:
            console.print(msg)
    def _rule(title: str = "") -> None:
        console.print(Rule(title, style="dim"))
except ImportError:
    def _print(msg: str, style: str = "") -> None:  # type: ignore[misc]
        print(msg)
    def _rule(title: str = "") -> None:  # type: ignore[misc]
        print(f"\n{'─' * 50} {title}")


# ─────────────────────────────────────────────────────────────────────────────
# Argument parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Appointment Letter Automation for AWS Student Builder Group",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  preview     Generate 3 sample PDFs for design calibration (no CSV needed)
  validate    Validate data/recipients.csv and print an error report
  run         Generate PDFs (default: dry run, no emails sent)

Examples:
  python main.py preview --guides
  python main.py validate
  python main.py run
  python main.py run --send
  python main.py run --send --test-email me@gmail.com
  python main.py run --send --only riya@college.edu
  python main.py run --send --team "Event Management"
  python main.py run --send --retry-failed
  python main.py run --force
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # ── preview ──
    preview_p = sub.add_parser("preview", help="Generate sample letters for design calibration")
    preview_p.add_argument(
        "--guides", action="store_true",
        help="Draw a red guide box showing the content area (useful for calibrating mm values)"
    )

    # ── validate ──
    sub.add_parser("validate", help="Validate data/recipients.csv without generating anything")

    # ── run ──
    run_p = sub.add_parser("run", help="Generate PDFs and optionally send emails")
    run_p.add_argument(
        "--send", action="store_true",
        help="Actually send emails (default: dry run, no emails sent)"
    )
    run_p.add_argument(
        "--test-email", metavar="EMAIL",
        help="Route ALL emails to this address instead of recipients (safe preview)"
    )
    run_p.add_argument(
        "--only", metavar="EMAIL",
        help="Process only this single recipient email address"
    )
    run_p.add_argument(
        "--team", metavar="TEAM",
        help='Process only recipients from this team (e.g. "Event Management")'
    )
    run_p.add_argument(
        "--retry-failed", action="store_true",
        help="Process only recipients whose last status was FAILED"
    )
    run_p.add_argument(
        "--force", action="store_true",
        help="Re-process recipients already marked SENT (dangerous: may re-send emails)"
    )
    run_p.add_argument(
        "--throttle", type=float, default=2.0, metavar="SECONDS",
        help="Seconds to wait between sending emails (default: 2)"
    )
    run_p.add_argument(
        "--reset-log", action="store_true",
        help="Delete send_log.csv before running (resets all statuses)"
    )

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────────────────────────────────────

def cmd_preview(args: argparse.Namespace) -> int:
    from src.config import load_config
    from src.pdf_gen import generate_previews, check_letterhead

    _rule("PREVIEW")
    config = load_config()
    template_dir = Path("templates")

    warning = check_letterhead(config)
    if warning:
        _print(f"⚠  {warning}", style="yellow")

    _print("Generating 3 sample letters (Lead / Member / long name)…")
    generate_previews(config, template_dir, show_guides=args.guides)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from src.config import load_config
    from src.validate import validate_csv, print_validation_report

    _rule("VALIDATE")
    config = load_config()
    csv_path = Path("data/recipients.csv")

    _print(f"Reading: {csv_path}")
    good_rows, errors = validate_csv(csv_path, config)
    all_valid = print_validation_report(good_rows, errors)
    return 0 if all_valid else 1


def cmd_run(args: argparse.Namespace) -> int:
    from src.config import load_config
    from src.validate import validate_csv, print_validation_report
    from src.pdf_gen import generate_pdf, role_title, generate_ref_id, check_letterhead
    from src.emailer import send_email
    from src import log as sendlog

    _rule("RUN")

    config      = load_config()
    csv_path    = Path("data/recipients.csv")
    output_dir  = Path("output")
    letters_dir = output_dir / "letters"
    template_dir = Path("templates")

    # ── Reset log if requested ──
    if args.reset_log:
        log_file = output_dir / "send_log.csv"
        if log_file.exists():
            log_file.unlink()
            _print("  ✓ Cleared send_log.csv", style="cyan")

    # ── Validate CSV ──
    _print(f"Validating: {csv_path}")
    good_rows, errors = validate_csv(csv_path, config)
    all_valid = print_validation_report(good_rows, errors)
    if not all_valid:
        _print("Fix validation errors first. Aborting.", style="red")
        return 1

    # ── Load existing log (idempotency) ──
    existing_log = sendlog.load_log(output_dir)

    # ── Apply filters ──
    filtered = good_rows

    if args.retry_failed:
        failed_emails = sendlog.get_failed_emails(existing_log)
        filtered = [r for r in filtered if r["email"] in failed_emails]
        _print(f"  --retry-failed: {len(filtered)} row(s) to retry")

    if args.only:
        filtered = [r for r in filtered if r["email"] == args.only]
        _print(f"  --only {args.only}: {len(filtered)} row(s) matched")

    if args.team:
        filtered = [r for r in filtered if r["team"] == args.team]
        _print(f"  --team '{args.team}': {len(filtered)} row(s) matched")

    if not filtered:
        _print("No recipients to process after filtering.", style="yellow")
        return 0

    # ── Letterhead check ──
    warning = check_letterhead(config)
    if warning:
        _print(f"⚠  {warning}", style="yellow")

    # ── Mode banner ──
    if not args.send:
        _print("\n[DRY RUN] PDFs will be generated; no emails will be sent.")
        _print("          Pass --send to actually send emails.\n", style="dim")
    elif args.test_email:
        _print(f"\n[TEST MODE] All emails → {args.test_email}\n", style="yellow")
    else:
        _print("\n[LIVE SEND] Emails will be sent to recipients.\n", style="bold red")

    # ── Build team counters for ref IDs ──
    team_counters: dict = {}

    # ── Process each recipient ──
    for recipient in filtered:
        email = recipient["email"]
        name  = recipient["name"]
        team  = recipient["team"]
        role  = recipient["role"]

        _rule(name)

        # Skip already-sent (unless --force)
        if not args.force and sendlog.is_already_sent(existing_log, email):
            _print(f"  ⏭  {name} ({email}) already SENT — skipping (use --force to override)")
            continue

        # Assign reference ID (stable: reuse if already in log)
        existing_entry = existing_log.get(email, {})
        if existing_entry.get("ref_id"):
            ref_id = existing_entry["ref_id"]
        else:
            team_code = config.team_code(team)
            team_counters[team_code] = team_counters.get(team_code, 0) + 1
            ref_id = generate_ref_id(
                config.reference_prefix, team_code, email, team_counters[team_code]
            )

        recipient["ref_id"] = ref_id

        # Mark PENDING
        sendlog.upsert_entry(
            existing_log, email,
            name=name, team=team, role=role, ref_id=ref_id,
            status=sendlog.STATUS_PENDING,
        )
        sendlog.save_log(output_dir, list(existing_log.values()))

        # ── Generate PDF ──
        pdf_filename = f"Appointment_Letter_{recipient['safe_name']}.pdf"
        pdf_path = letters_dir / pdf_filename

        try:
            _print(f"  📄 Generating PDF: {pdf_filename}")
            generate_pdf(recipient, pdf_path, config, template_dir)
            sendlog.upsert_entry(
                existing_log, email,
                name=name, team=team, role=role, ref_id=ref_id,
                status=sendlog.STATUS_GENERATED,
            )
            sendlog.save_log(output_dir, list(existing_log.values()))
            _print(f"     ✓ PDF saved: {pdf_path}", style="green")
        except Exception as exc:
            _print(f"     ✗ PDF failed for {name}: {exc}", style="red")
            sendlog.upsert_entry(
                existing_log, email,
                name=name, team=team, role=role, ref_id=ref_id,
                status=sendlog.STATUS_FAILED, error=str(exc),
            )
            sendlog.save_log(output_dir, list(existing_log.values()))
            continue

        # ── Send (or dry-run) email ──
        try:
            send_email(
                recipient=recipient,
                pdf_path=pdf_path,
                config=config,
                template_dir=template_dir,
                test_email=args.test_email if args.send else None,
                dry_run=not args.send,
            )
            if args.send:
                sendlog.upsert_entry(
                    existing_log, email,
                    name=name, team=team, role=role, ref_id=ref_id,
                    status=sendlog.STATUS_SENT,
                )
                _print(f"     ✓ Email sent to {args.test_email or email}", style="green")
            else:
                # Dry run: leave as GENERATED (email not sent)
                pass

            sendlog.save_log(output_dir, list(existing_log.values()))
        except Exception as exc:
            _print(f"     ✗ Email failed for {name}: {exc}", style="red")
            sendlog.upsert_entry(
                existing_log, email,
                name=name, team=team, role=role, ref_id=ref_id,
                status=sendlog.STATUS_FAILED, error=str(exc),
            )
            sendlog.save_log(output_dir, list(existing_log.values()))

        # Throttle between sends
        if args.send and filtered.index(recipient) < len(filtered) - 1:
            time.sleep(args.throttle)

    # ── Summary ──
    _rule("SUMMARY")
    sendlog.print_summary(existing_log)
    _print(f"\nLog file: {output_dir / 'send_log.csv'}")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "preview":
            sys.exit(cmd_preview(args))
        elif args.command == "validate":
            sys.exit(cmd_validate(args))
        elif args.command == "run":
            sys.exit(cmd_run(args))
        else:
            parser.print_help()
            sys.exit(1)
    except KeyboardInterrupt:
        _print("\n\nAborted by user (Ctrl+C).", style="yellow")
        sys.exit(130)
    except Exception as exc:
        _print(f"\n✗ Fatal error: {exc}", style="bold red")
        raise


if __name__ == "__main__":
    main()
