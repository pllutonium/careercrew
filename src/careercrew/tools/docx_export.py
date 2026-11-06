"""Professional ATS-Optimized Document Export and Headless PDF Conversion Tool."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Union

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from careercrew.schemas.resume import TailoredResume, TailoredSection

logger = logging.getLogger(__name__)


def _set_cell_margins(cell, top=0, bottom=0, left=0, right=0):
    """Set zero margins on table cells for precise layout alignment."""
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for side, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def _add_bottom_border(paragraph, color: str = "2B4C7E", sz: str = "12"):
    """Adds a sleek bottom accent border to section headings without namespace corruption."""
    pPr = paragraph._element.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), sz)  # 12 = 1.5 pt
    bottom.set(qn("w:space"), "3")
    bottom.set(qn("w:color"), color)
    pBdr.append(bottom)
    pPr.append(pBdr)


def generate_resume_docx(
    resume: TailoredResume,
    output_path: Union[str, Path],
    profile_meta: Optional[Dict[str, Any]] = None,
    include_source_tags: bool = False,
    font_name: str = "Calibri",
) -> Path:
    """Exports a TailoredResume instance to an ATS-optimized Microsoft Word (.docx) document.

    Formatting specifications:
    - 0.65-inch margins (46.8 pt) across all sections
    - Font hierarchy:
        * Candidate Name: 16pt Bold
        * Contact: 9pt Muted
        * Section Headings: 11pt Bold Uppercase with bottom border line
        * Role / Organization / Date: 10pt Bold / Italic
        * Bullets: 9.5pt body text with 1.15 line spacing and 2pt paragraph spacing
        * Optional source tags: 7.5pt muted superscript
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = docx.Document()

    # Configure exact 0.65-inch (46.8 pt) margins across all sections
    for sec in doc.sections:
        sec.top_margin = Pt(46.8)
        sec.bottom_margin = Pt(46.8)
        sec.left_margin = Pt(46.8)
        sec.right_margin = Pt(46.8)

    meta = profile_meta or {}
    name = meta.get("name") or "CANDIDATE NAME"
    email = meta.get("email") or ""
    phone = meta.get("phone") or ""
    location = meta.get("location") or ""
    linkedin = meta.get("linkedin") or ""

    # Header: Candidate Name
    p_name = doc.add_paragraph()
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_name.paragraph_format.space_before = Pt(0)
    p_name.paragraph_format.space_after = Pt(2)
    run_name = p_name.add_run(name)
    run_name.font.name = font_name
    run_name.font.size = Pt(16)
    run_name.font.bold = True
    run_name.font.color.rgb = RGBColor(30, 41, 59)

    # Header: Contact Info Line
    contact_parts = [part for part in [email, phone, location, linkedin] if part]
    if contact_parts:
        p_contact = doc.add_paragraph()
        p_contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_contact.paragraph_format.space_before = Pt(0)
        p_contact.paragraph_format.space_after = Pt(8)
        run_contact = p_contact.add_run(" | ".join(contact_parts))
        run_contact.font.name = font_name
        run_contact.font.size = Pt(9)
        run_contact.font.color.rgb = RGBColor(100, 116, 139)

    # Executive Summary Section
    if resume.summary and resume.summary.text:
        _render_section_heading(doc, "PROFESSIONAL SUMMARY", font_name)
        p_sum = doc.add_paragraph()
        p_sum.paragraph_format.space_before = Pt(2)
        p_sum.paragraph_format.space_after = Pt(6)
        p_sum.paragraph_format.line_spacing = 1.15
        run_sum = p_sum.add_run(resume.summary.text)
        run_sum.font.name = font_name
        run_sum.font.size = Pt(9.5)
        run_sum.font.color.rgb = RGBColor(30, 41, 59)

        if include_source_tags and resume.summary.source_ids:
            run_src = p_sum.add_run(f" [src: {', '.join(resume.summary.source_ids)}]")
            run_src.font.name = font_name
            run_src.font.size = Pt(7.5)
            run_src.font.italic = True
            run_src.font.color.rgb = RGBColor(148, 163, 184)

    # Structured Resume Sections
    for section in resume.sections:
        _render_section_heading(doc, section.section_name.upper(), font_name)
        _render_section_content(doc, section, font_name, include_source_tags)

    doc.save(str(out_file))
    return out_file


# Backwards compatibility alias
export_to_docx = generate_resume_docx


def _render_section_heading(doc: docx.Document, heading_text: str, font_name: str) -> None:
    """Renders a section title with 11pt bold typography and a bottom border line."""
    p_head = doc.add_paragraph()
    p_head.paragraph_format.space_before = Pt(8)
    p_head.paragraph_format.space_after = Pt(3)
    p_head.paragraph_format.keep_with_next = True

    run = p_head.add_run(heading_text)
    run.font.name = font_name
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.color.rgb = RGBColor(15, 23, 42)

    _add_bottom_border(p_head, color="2B4C7E", sz="10")


def _render_section_content(
    doc: docx.Document,
    section: TailoredSection,
    font_name: str,
    include_source_tags: bool,
) -> None:
    """Renders the organization, role title, dates, and bullets for a section,
    gracefully handling missing optional fields.
    """
    has_meta = bool(section.organization or section.role_title or section.date_range)
    if has_meta:
        # Use single-column paragraph with right tab stop for 100% ATS parser compatibility
        p_meta = doc.add_paragraph()
        p_meta.paragraph_format.space_before = Pt(3)
        p_meta.paragraph_format.space_after = Pt(1)
        p_meta.paragraph_format.keep_with_next = True
        p_meta.paragraph_format.tab_stops.add_tab_stop(Inches(7.2), WD_TAB_ALIGNMENT.RIGHT)

        if section.role_title:
            r_role = p_meta.add_run(section.role_title)
            r_role.font.name = font_name
            r_role.font.size = Pt(10)
            r_role.font.bold = True
            r_role.font.color.rgb = RGBColor(15, 23, 42)

        if section.organization:
            sep = "  |  " if section.role_title else ""
            r_org = p_meta.add_run(f"{sep}{section.organization}")
            r_org.font.name = font_name
            r_org.font.size = Pt(10)
            r_org.font.italic = True
            r_org.font.color.rgb = RGBColor(51, 65, 85)

        if section.date_range:
            prefix = "\t" if (section.role_title or section.organization) else ""
            r_date = p_meta.add_run(f"{prefix}{section.date_range}")
            r_date.font.name = font_name
            r_date.font.size = Pt(9.5)
            r_date.font.italic = True
            r_date.font.color.rgb = RGBColor(100, 116, 139)

    # Render Bullets
    for bullet in (section.bullets or []):
        p_bullet = doc.add_paragraph(style="List Bullet")
        p_bullet.paragraph_format.space_before = Pt(0)
        p_bullet.paragraph_format.space_after = Pt(2)
        p_bullet.paragraph_format.line_spacing = 1.15

        r_text = p_bullet.add_run(bullet.text)
        r_text.font.name = font_name
        r_text.font.size = Pt(9.5)
        r_text.font.color.rgb = RGBColor(30, 41, 59)

        if include_source_tags and bullet.source_ids:
            r_src = p_bullet.add_run(f" [src: {', '.join(bullet.source_ids)}]")
            r_src.font.name = font_name
            r_src.font.size = Pt(7.5)
            r_src.font.italic = True
            r_src.font.color.rgb = RGBColor(148, 163, 184)


def find_libreoffice_binary() -> Optional[str]:
    """Finds available LibreOffice or soffice executable across platforms."""
    candidates = [
        "libreoffice",
        "soffice",
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if shutil.which(candidate) or (os.path.isfile(candidate) and os.access(candidate, os.X_OK)):
            return candidate
    return None


def convert_docx_to_pdf(
    docx_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    timeout_seconds: int = 45,
) -> Path:
    """Converts a DOCX file to PDF using headless LibreOffice."""
    in_file = Path(docx_path).resolve()
    if not in_file.exists():
        raise FileNotFoundError(f"Input DOCX file not found: {in_file}")

    target_dir = Path(output_dir).resolve() if output_dir else in_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    expected_pdf = target_dir / f"{in_file.stem}.pdf"

    lo_bin = find_libreoffice_binary()
    if not lo_bin:
        msg = (
            "LibreOffice headless binary ('libreoffice' or 'soffice') "
            "was not found on PATH or common installation paths."
        )
        logger.error(msg)
        raise FileNotFoundError(msg)

    cmd = [
        lo_bin,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(target_dir),
        str(in_file),
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr_msg = exc.stderr.strip() if exc.stderr else "No stderr output"
        stdout_msg = exc.stdout.strip() if exc.stdout else "No stdout output"
        msg = (
            f"LibreOffice headless conversion failed with exit code {exc.returncode}.\n"
            f"STDOUT: {stdout_msg}\n"
            f"STDERR: {stderr_msg}"
        )
        logger.error(msg)
        raise RuntimeError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"Headless PDF conversion timed out after {timeout_seconds} seconds."
        logger.error(msg)
        raise RuntimeError(msg) from exc

    if not expected_pdf.exists():
        msg = (
            f"LibreOffice conversion completed (output: {result.stdout.strip()}) "
            f"but expected PDF was not found at {expected_pdf}"
        )
        logger.error(msg)
        raise RuntimeError(msg)

    return expected_pdf
