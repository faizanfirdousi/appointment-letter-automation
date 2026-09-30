"""
src/pdf_gen.py
Renders a personalized Appointment Letter PDF using Jinja2 + Playwright.

Design:
  - Letterhead PNG is Layer 1 (CSS background).
  - HTML letter text is Layer 2, positioned in the empty content area.
  - Fonts loaded from local .ttf via @font-face — must match the design.
  - print_background=True ensures letterhead appears in the PDF.
  - Font auto-shrinks to min_font_size_pt if content overflows.
"""

import asyncio
import base64
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape

from src.config import Config


# ─────────────────────────────────────────────────────────────────────────────
# Role wording (letter-content-update.md §3)
# ─────────────────────────────────────────────────────────────────────────────

ROLE_PHRASES = {
    "Lead":    "the Team Lead of",
    "Co-Lead": "the Team Co-Lead of",
    "Member":  "a member of",
}

ROLE_TITLES = {
    "Lead":    "Team Lead",
    "Co-Lead": "Team Co-Lead",
    "Member":  "Team Member",
}


def role_phrase(role: str) -> str:
    return ROLE_PHRASES.get(role, role)


def role_title(role: str) -> str:
    return ROLE_TITLES.get(role, role)


# ─────────────────────────────────────────────────────────────────────────────
# Reference ID generation (F12)
# ─────────────────────────────────────────────────────────────────────────────

def generate_ref_id(prefix: str, team_code: str, email: str, counter: int) -> str:
    """Generate a stable reference ID like AWSSBG-2026-EM-001."""
    return f"{prefix}-{team_code}-{counter:03d}"


# ─────────────────────────────────────────────────────────────────────────────
# Asset helpers
# ─────────────────────────────────────────────────────────────────────────────

def _file_to_data_uri(path: Path, mime: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _asset_uri(asset_path: Path, mime: str) -> str:
    if not asset_path or not asset_path.is_file():
        return ""
    return _file_to_data_uri(asset_path, mime)


def _letterhead_uri(config: Config) -> str:
    img_path = config.abs_asset(config.letterhead.image)
    ext = img_path.suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    return _asset_uri(img_path, mime)


def _font_uri(config: Config, bold: bool = False) -> str:
    font_file = (
        config.letterhead.font_file_bold if bold
        else config.letterhead.font_file_regular
    )
    font_path = config.abs_asset(font_file)
    return _asset_uri(font_path, "font/ttf")


# ─────────────────────────────────────────────────────────────────────────────
# Letterhead sanity check
# ─────────────────────────────────────────────────────────────────────────────

def check_letterhead(config: Config) -> Optional[str]:
    """Return a warning string if letterhead is missing or wrong aspect ratio."""
    img_path = config.abs_asset(config.letterhead.image)
    if not img_path.exists():
        return (
            f"Letterhead image not found: {img_path}\n"
            "Please add your A4 letterhead PNG to assets/letterhead.png\n"
            "Or run: python scripts/create_sample_letterhead.py"
        )
    try:
        from PIL import Image as PilImage
        with PilImage.open(img_path) as im:
            w, h = im.size
        a4_ratio = 210 / 297
        actual_ratio = w / h
        if abs(actual_ratio - a4_ratio) > 0.02:
            return (
                f"WARNING: Letterhead aspect ratio {actual_ratio:.3f} "
                f"(expected ~{a4_ratio:.3f} for A4 portrait). "
                f"Actual size: {w}x{h}."
            )
    except ImportError:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Build the full template context for a recipient
# ─────────────────────────────────────────────────────────────────────────────

def build_template_context(
    recipient: Dict[str, Any],
    config: Config,
    font_size_pt: float,
    show_guides: bool = False,
) -> Dict[str, Any]:
    """
    Assemble all variables passed to letter.html (and email templates).
    This is the single source of truth for what placeholders are available.
    """
    name      = recipient["name"]
    role      = recipient["role"]
    team      = recipient["team"]
    first_name = name.split()[0]
    r_phrase  = role_phrase(role)
    r_title   = role_title(role)

    # Responsibility text from config
    tc = config.teams.get(team)
    responsibility = tc.responsibility if tc else ""

    # Render lead_addition as a Jinja2 string (it contains {{ role_title }})
    lead_addition_rendered = ""
    if role in ("Lead", "Co-Lead") and config.lead_addition:
        lead_addition_rendered = Template(config.lead_addition).render(
            role_title=r_title
        )

    return {
        # Recipient
        "name":             name,
        "first_name":       first_name,
        "email":            recipient["email"],
        "team":             team,
        "role":             role,
        "role_phrase":      r_phrase,
        "role_title":       r_title,
        "roll_no":          recipient.get("roll_no", ""),
        "year":             recipient.get("year", ""),
        "department":       recipient.get("department", ""),
        "ref_id":           recipient.get("ref_id", ""),
        # Content
        "responsibility":        responsibility,
        "lead_addition":         lead_addition_rendered,
        # Config
        "issue_date":            config.resolved_issue_date(),
        "club_name":             config.club_name,
        "college_name":          config.college_name,
        "academic_year":         config.academic_year,
        "captain_name":          config.captain_name,
        "faculty_coordinator":   config.faculty_coordinator,
        "tenure":                config.tenure,
        "issuer_name":           config.issuer_name,
        "issuer_designation":    config.issuer_designation,
        "print_closing":         config.print_closing,
        "closing_line":          config.closing_line,
        "onboarding_link":       config.onboarding_link,
        "onboarding_datetime":   config.onboarding_datetime,
        # Layout / design
        "letterhead_uri":    _letterhead_uri(config),
        "font_regular_uri":  _font_uri(config, bold=False),
        "font_bold_uri":     _font_uri(config, bold=True),
        "font_family":       config.letterhead.font_family,
        "font_size_pt":      font_size_pt,
        "text_color":        config.letterhead.text_color,
        "content_top_mm":    config.letterhead.content_top_mm,
        "content_bottom_mm": config.letterhead.content_bottom_mm,
        "content_left_mm":   config.letterhead.content_left_mm,
        "content_right_mm":  config.letterhead.content_right_mm,
        "show_guides":       show_guides,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HTML rendering
# ─────────────────────────────────────────────────────────────────────────────

def _render_html(
    template_dir: Path,
    recipient: Dict[str, Any],
    config: Config,
    font_size_pt: float,
    show_guides: bool = False,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )
    tpl = env.get_template("letter.html")
    ctx = build_template_context(recipient, config, font_size_pt, show_guides)
    return tpl.render(**ctx)


# ─────────────────────────────────────────────────────────────────────────────
# PDF generation (Playwright async core)
# ─────────────────────────────────────────────────────────────────────────────

async def _render_pdf_async(
    output_path: Path,
    config: Config,
    font_size_pt: float,
    template_dir: Path,
    recipient: Dict[str, Any],
    show_guides: bool = False,
) -> None:
    from playwright.async_api import async_playwright

    min_size = config.letterhead.min_font_size_pt
    current_size = font_size_pt

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        while True:
            rendered_html = _render_html(
                template_dir, recipient, config, current_size, show_guides
            )
            await page.set_content(rendered_html, wait_until="networkidle")
            await page.evaluate("document.fonts.ready")

            # Check if .content div overflows
            overflows = await page.evaluate(
                """() => {
                    const el = document.querySelector('.content');
                    if (!el) return false;
                    return el.scrollHeight > el.clientHeight + 2;
                }"""
            )

            if not overflows or current_size <= min_size:
                if overflows and current_size <= min_size:
                    raise RuntimeError(
                        f"Text for '{recipient.get('name', '?')}' overflows even at "
                        f"minimum font size ({min_size}pt). Shorten the template or "
                        f"increase content area margins in config.yaml."
                    )
                break

            current_size = round(current_size - 0.5, 1)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        await page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
        )
        await browser.close()


def generate_pdf(
    recipient: Dict[str, Any],
    output_path: Path,
    config: Config,
    template_dir: Path,
    show_guides: bool = False,
) -> None:
    """Synchronous wrapper — call this from the rest of the app."""
    asyncio.run(
        _render_pdf_async(
            output_path=output_path,
            config=config,
            font_size_pt=config.letterhead.font_size_pt,
            template_dir=template_dir,
            recipient=recipient,
            show_guides=show_guides,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Preview mode
# ─────────────────────────────────────────────────────────────────────────────

def _make_preview_samples(config: Config) -> list:
    """Build 3 sample recipients using the first available teams from config."""
    team_names = list(config.teams.keys())
    # Pick Event Management (Lead), Technical (Member), and a third team (Co-Lead)
    def pick(preference, index):
        return preference if preference in team_names else (team_names[index] if index < len(team_names) else team_names[0])

    t_lead   = pick("Event Management", 0)
    t_member = pick("Technical", 1)
    t_colead = pick("Design", 2)

    prefix = config.reference_prefix
    tc_lead   = config.teams[t_lead]
    tc_member = config.teams[t_member]
    tc_colead = config.teams[t_colead]

    return [
        {
            "name": "Riya Sharma", "email": "riya@example.com",
            "team": t_lead, "role": "Lead",
            "roll_no": "22CS101", "year": "2nd Year", "department": "CSE",
            "ref_id": f"{prefix}-{tc_lead.code}-001", "safe_name": "Riya_Sharma",
        },
        {
            "name": "Arjun Patel", "email": "arjun@example.com",
            "team": t_member, "role": "Member",
            "roll_no": "23IT045", "year": "1st Year", "department": "IT",
            "ref_id": f"{prefix}-{tc_member.code}-001", "safe_name": "Arjun_Patel",
        },
        {
            # Long name edge case
            "name": "Bartholomew Krishnamurthy Raghunathan",
            "email": "bart@example.com",
            "team": t_colead, "role": "Co-Lead",
            "roll_no": "", "year": "3rd Year", "department": "Architecture",
            "ref_id": f"{prefix}-{tc_colead.code}-001",
            "safe_name": "Bartholomew_Krishnamurthy_Raghunathan",
        },
    ]


def generate_previews(config: Config, template_dir: Path, show_guides: bool = False) -> None:
    """Render 3 sample PDFs into output/preview/ for design calibration."""
    preview_dir = config.project_root / "output" / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    warning = check_letterhead(config)
    if warning:
        try:
            from rich.console import Console
            Console().print(f"[yellow]{warning}[/yellow]")
        except ImportError:
            print(warning)

    samples = _make_preview_samples(config)
    for sample in samples:
        out_path = preview_dir / f"Preview_{sample['safe_name']}.pdf"
        try:
            from rich.console import Console
            Console().print(f"  Generating preview: [cyan]{out_path.name}[/cyan]")
        except ImportError:
            print(f"  Generating preview: {out_path.name}")

        generate_pdf(sample, out_path, config, template_dir, show_guides=show_guides)

    try:
        from rich.console import Console
        c = Console()
        c.print(f"\n[green]✓ Previews written to: {preview_dir}[/green]")
        if show_guides:
            c.print(
                "[yellow]  Red guide box shows the content area. "
                "Adjust content_*_mm in config.yaml to tune.[/yellow]\n"
            )
    except ImportError:
        print(f"\n✓ Previews written to: {preview_dir}")
