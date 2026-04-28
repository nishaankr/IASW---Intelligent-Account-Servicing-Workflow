"""Generate a synthetic Marriage Certificate PDF for the demo flow.

The output is a plausibly-shaped Marriage Certificate that the extraction
agent can parse into structured fields. NOT a forgery — clearly synthetic
and labelled as such; just has the visual structure (header, registrar
block, signature area) that the extraction prompt's heuristics expect.

Run with:
    python samples/generate_sample_cert.py

Output:
    samples/marriage_certificate_priya.pdf
"""

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# Document data (the canonical demo case) 
BRIDE_NAME = "Priya Sharma"
GROOM_NAME = "Arjun Mehta"
MARRIED_NAME = "Priya Mehta"
DATE_OF_MARRIAGE = date(2025, 6, 14)
ISSUE_DATE = date(2025, 6, 20)
CERTIFICATE_NUMBER = "MC-2025-BLR-004217"
ISSUING_AUTHORITY = "Office of the Registrar of Marriages, Bengaluru, Karnataka"

OUTPUT_PATH = Path(__file__).parent / "marriage_certificate_priya.pdf"


def build_certificate() -> None:
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Marriage Certificate (Synthetic Demo)",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontSize=22,
        spaceAfter=16,
        alignment=1,
    )
    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Heading2"],
        fontSize=14,
        alignment=1,
        textColor=colors.HexColor("#444444"),
        spaceAfter=24,
    )
    body_style = ParagraphStyle(
        "body", parent=styles["Normal"], fontSize=12, leading=18,
    )
    small_italic = ParagraphStyle(
        "small",
        parent=styles["Italic"],
        fontSize=9,
        textColor=colors.gray,
    )

    story = []

    # Header
    story.append(Paragraph(ISSUING_AUTHORITY, subtitle_style))
    story.append(Paragraph("MARRIAGE CERTIFICATE", title_style))

    # Body paragraph (the prose statement)
    story.append(Paragraph(
        f"This is to certify that the marriage of "
        f"<b>{BRIDE_NAME}</b> (bride) and <b>{GROOM_NAME}</b> (groom) "
        f"was duly solemnised on <b>{DATE_OF_MARRIAGE.strftime('%d %B %Y')}</b> "
        f"and registered under the Hindu Marriage Act, 1955, at the office "
        f"named above.",
        body_style,
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        f"Pursuant to this marriage, the bride has assumed the legal name "
        f"<b>{MARRIED_NAME}</b>.",
        body_style,
    ))
    story.append(Spacer(1, 24))

    # Particulars table — the structured block the extraction agent reads.
    data = [
        ["Bride's Name (pre-marriage)", BRIDE_NAME],
        ["Groom's Name", GROOM_NAME],
        ["Married Name (post-marriage)", MARRIED_NAME],
        ["Date of Marriage", DATE_OF_MARRIAGE.isoformat()],
        ["Certificate Number", CERTIFICATE_NUMBER],
        ["Date of Issue", ISSUE_DATE.isoformat()],
        ["Issuing Authority", ISSUING_AUTHORITY],
    ]
    table = Table(data, colWidths=[7 * cm, 9 * cm])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 11),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 36))

    # Signature / seal block — visual cue for the document_structure heuristic.
    sig = Table(
        [
            ["", ""],
            ["___________________________", "___________________________"],
            ["Registrar's Signature", "Official Seal"],
        ],
        colWidths=[8 * cm, 8 * cm],
    )
    sig.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(sig)
    story.append(Spacer(1, 24))

    # Synthetic disclaimer 
    story.append(Paragraph(
        "[ SYNTHETIC DOCUMENT — generated for the IASW prototype demo. "
        "Not a real legal instrument. ]",
        small_italic,
    ))

    doc.build(story)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    build_certificate()