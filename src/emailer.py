"""
src/emailer.py
Sends personalized emails with the appointment letter PDF attached.
Uses smtplib + Gmail SMTP (STARTTLS on port 587).
Retries up to 3 times per recipient with exponential back-off.
"""

import smtplib
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import Config

MAX_RETRIES   = 3
RETRY_DELAYS  = [5, 15, 30]   # seconds between retry attempts


def _render_email(
    template_dir: Path,
    template_name: str,
    recipient: Dict[str, Any],
    config: Config,
) -> str:
    """Render an email template (HTML or plain text) with Jinja2."""
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )
    tpl = env.get_template(template_name)
    first_name = recipient["name"].split()[0]

    ctx = {
        "name":                  recipient["name"],
        "first_name":            first_name,
        "team":                  recipient["team"],
        "role":                  recipient["role"],
        "role_title":            recipient.get("role_title", recipient["role"]),
        "ref_id":                recipient.get("ref_id", ""),
        "issue_date":            config.resolved_issue_date(),
        "club_name":             config.club_name,
        "college_name":          config.college_name,
        "academic_year":         config.academic_year,
        "issuer_name":           config.issuer_name,
        "issuer_designation":    config.issuer_designation,
        "onboarding_link":       config.onboarding_link,
        "onboarding_datetime":   config.onboarding_datetime,
        "merch_form_link":       getattr(config, "merch_form_link", ""),
    }
    return tpl.render(**ctx)


def _render_subject(config: Config, recipient: Dict[str, Any]) -> str:
    """Render the email subject line via Jinja2."""
    from jinja2 import Template
    first_name = recipient["name"].split()[0]
    return Template(config.email_subject).render(
        first_name=first_name,
        team=recipient["team"],
        role=recipient["role"],
    )


def send_email(
    recipient: Dict[str, Any],
    pdf_path: Path,
    config: Config,
    template_dir: Path,
    test_email: Optional[str] = None,
    dry_run: bool = True,
    extra_attachments: Optional[List[Path]] = None,
) -> None:
    """
    Compose and send (or dry-run) the appointment letter email.

    Args:
        recipient:   Dict with name, email, team, role, ref_id, etc.
        pdf_path:    Absolute path to the generated PDF.
        config:      Loaded Config object.
        template_dir:Path to the templates/ directory.
        test_email:  If set, deliver to this address instead of recipient.
        dry_run:     If True, print what would be sent but do NOT connect to SMTP.
        extra_attachments: Optional list of additional Path objects to attach.

    Raises:
        smtplib.SMTPException on final failure (after retries).
    """
    from src.pdf_gen import role_title

    # Augment recipient dict with role_title for templates
    recipient = dict(recipient)
    recipient["role_title"] = role_title(recipient["role"])

    to_address = test_email if test_email else recipient["email"]
    subject    = _render_subject(config, recipient)

    # Render email body
    body_html  = _render_email(template_dir, "email.html", recipient, config)
    body_plain = _render_email(template_dir, "email.txt",  recipient, config)

    # PDF attachment
    pdf_filename = f"Appointment_Letter_{recipient['safe_name']}.pdf"

    # Additional attachments (e.g., Team List PDF)
    attachments_to_add: List[Path] = []
    if extra_attachments is not None:
        attachments_to_add = list(extra_attachments)
    else:
        team_pdf_setting = getattr(config, "team_list_pdf", "aws_team_list - Team List.pdf")
        if team_pdf_setting:
            team_pdf_path = Path(team_pdf_setting)
            if not team_pdf_path.is_absolute():
                team_pdf_path = config.project_root / team_pdf_path
            if team_pdf_path.exists():
                attachments_to_add.append(team_pdf_path)

    if dry_run:
        _print_dry_run(recipient, to_address, subject, pdf_path, pdf_filename, attachments_to_add)
        return

    # Compose the message
    msg = EmailMessage()
    msg["Subject"]  = subject
    msg["From"]     = f"{config.from_name} <{config.smtp_user}>"
    msg["To"]       = to_address
    msg["Reply-To"] = config.smtp_user
    msg.set_content(body_plain)  # plain-text part first
    msg.add_alternative(body_html, subtype="html")

    if pdf_path.exists():
        with open(pdf_path, "rb") as fh:
            msg.add_attachment(
                fh.read(),
                maintype="application",
                subtype="pdf",
                filename=pdf_filename,
            )

    for att in attachments_to_add:
        if att.exists():
            with open(att, "rb") as fh:
                msg.add_attachment(
                    fh.read(),
                    maintype="application",
                    subtype="pdf",
                    filename=att.name,
                )

    # Send with retry
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(config.smtp_user, config.smtp_app_password)
                smtp.send_message(msg)
            return  # success
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                _log_retry(recipient["email"], attempt + 1, delay, exc)
                time.sleep(delay)

    # All retries exhausted
    raise last_exc  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# Pretty console output helpers
# ─────────────────────────────────────────────────────────────────────────────

def _print_dry_run(
    recipient: Dict,
    to_address: str,
    subject: str,
    pdf_path: Path,
    pdf_filename: str,
    extra_attachments: Optional[List[Path]] = None,
) -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel

        extra_text = ""
        if extra_attachments:
            for att in extra_attachments:
                extra_text += f"\n[bold]Attach:[/bold]   {att.name} (exists: {att.exists()})"

        console = Console()
        console.print(
            Panel(
                f"[bold]To:[/bold]      {to_address}\n"
                f"[bold]Subject:[/bold] {subject}\n"
                f"[bold]PDF:[/bold]     {pdf_filename} (exists: {pdf_path.exists()})"
                f"{extra_text}",
                title=f"[yellow]DRY RUN — {recipient['name']}[/yellow]",
                border_style="yellow",
            )
        )
    except ImportError:
        print(f"\n[DRY RUN] To: {to_address}")
        print(f"          Subject: {subject}")
        print(f"          PDF: {pdf_filename} (exists: {pdf_path.exists()})")
        if extra_attachments:
            for att in extra_attachments:
                print(f"          Attach: {att.name} (exists: {att.exists()})")


def _log_retry(email: str, attempt: int, delay: int, exc: Exception) -> None:
    try:
        from rich.console import Console
        Console().print(
            f"  [yellow]Retry {attempt}/{MAX_RETRIES} for {email} "
            f"in {delay}s ({exc})[/yellow]"
        )
    except ImportError:
        print(f"  Retry {attempt}/{MAX_RETRIES} for {email} in {delay}s ({exc})")
