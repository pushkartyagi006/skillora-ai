"""Builds a one-page A4 resume PDF in the same layout as the sample resume:
centered navy name, grey contact lines, navy section headings with a rule,
bold entry titles with right-aligned dates, italic grey sub-lines and bullets."""

import io
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = HexColor("#1F3A5F")
GREY = HexColor("#555555")
DARK = HexColor("#111111")

MARGIN_X = 42
MARGIN_Y = 34
CONTENT_W = A4[0] - 2 * MARGIN_X

REPLACEMENTS = {
    "\u2192": "->", "\u2190": "<-", "\u2265": ">=", "\u2264": "<=", "\u2212": "-",
    "\u2011": "-", "\u00a0": " ", "\u200b": "", "\u2713": "", "\u2714": "",
    "\u25cf": "\u2022", "\u25aa": "\u2022", "\u2022": "\u2022",
}
SUPERSCRIPTS = {"\u00b2": "2", "\u00b3": "3", "\u00b9": "1"}
SUBSCRIPTS = {chr(0x2080 + i): str(i) for i in range(10)}


def fmt(value) -> str:
    """Make text safe for ReportLab's built-in fonts and mini-HTML."""
    text = "" if value is None else str(value)
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    for old, new in SUPERSCRIPTS.items():
        text = text.replace(old, "@@SUP@@" + new + "@@/SUP@@")
    for old, new in SUBSCRIPTS.items():
        text = text.replace(old, "@@SUB@@" + new + "@@/SUB@@")
    text = text.encode("cp1252", "replace").decode("cp1252")
    text = escape(text.replace("\n", " ").strip())
    return (
        text.replace("@@SUP@@", "<super>").replace("@@/SUP@@", "</super>")
        .replace("@@SUB@@", "<sub>").replace("@@/SUB@@", "</sub>")
    )


def as_str(value) -> str:
    return "" if value is None else str(value).strip()


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v not in (None, "")]
    return [value]


def as_dicts(value) -> list:
    return [v for v in as_list(value) if isinstance(v, dict)]


def make_styles(s: float) -> dict:
    base = 9.5 * s
    lead = 12.4 * s
    return {
        "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=22 * s,
                               leading=26 * s, alignment=TA_CENTER, textColor=NAVY),
        "title": ParagraphStyle("title", fontName="Helvetica", fontSize=10 * s,
                                leading=13 * s, alignment=TA_CENTER, textColor=GREY),
        "contact": ParagraphStyle("contact", fontName="Helvetica", fontSize=base,
                                  leading=lead, alignment=TA_CENTER, textColor=GREY),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5 * s,
                             leading=14 * s, textColor=NAVY, spaceBefore=8 * s, spaceAfter=1),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=base,
                               leading=lead, textColor=DARK),
        "etitle": ParagraphStyle("etitle", fontName="Helvetica-Bold", fontSize=base + 0.5 * s,
                                 leading=lead, textColor=DARK),
        "date": ParagraphStyle("date", fontName="Helvetica", fontSize=base,
                               leading=lead, alignment=TA_RIGHT, textColor=GREY),
        "sub": ParagraphStyle("sub", fontName="Helvetica-Oblique", fontSize=base,
                              leading=lead, textColor=HexColor("#444444")),
        "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=base,
                                 leading=lead, leftIndent=14, bulletIndent=4, textColor=DARK),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=base,
                                leading=lead, textColor=DARK),
    }


def build_story(r: dict, s: float) -> list:
    st = make_styles(s)
    story = []

    def heading(text):
        story.append(Paragraph(fmt(text).upper(), st["h2"]))
        story.append(HRFlowable(width="100%", thickness=0.8, color=NAVY,
                                spaceBefore=1, spaceAfter=4 * s))

    def entry_head(left, right):
        t = Table(
            [[Paragraph(fmt(left), st["etitle"]), Paragraph(fmt(right), st["date"])]],
            colWidths=[CONTENT_W - 120, 120],
        )
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(t)

    def bullets(items):
        for b in as_list(items):
            story.append(Paragraph(fmt(b), st["bullet"], bulletText="\u2022"))

    # ---- header ----
    story.append(Paragraph(fmt(as_str(r.get("name")).upper() or "YOUR NAME"), st["name"]))
    if as_str(r.get("title")):
        story.append(Paragraph(fmt(r.get("title")), st["title"]))
    c = r.get("contact") if isinstance(r.get("contact"), dict) else {}
    line1 = [as_str(c.get(k)) for k in ("phone", "email", "location") if as_str(c.get(k))]
    line2 = [as_str(x) for x in as_list(c.get("links")) if as_str(x)]
    if line1:
        story.append(Paragraph("  |  ".join(fmt(x) for x in line1), st["contact"]))
    if line2:
        story.append(Paragraph("  |  ".join(fmt(x) for x in line2), st["contact"]))

    # ---- summary ----
    if as_str(r.get("summary")):
        heading("Professional Summary")
        story.append(Paragraph(fmt(r.get("summary")), st["body"]))

    # ---- education ----
    edu = as_dicts(r.get("education"))
    if edu:
        heading("Education")
        for e in edu:
            entry_head(e.get("title") or e.get("degree") or "", e.get("period"))
            sub = e.get("subtitle") or " | ".join(
                x for x in (as_str(e.get("institution")), as_str(e.get("details"))) if x)
            if as_str(sub):
                story.append(Paragraph(fmt(sub), st["sub"]))
            if as_str(e.get("note")):
                story.append(Paragraph(fmt(e.get("note")), st["body"]))

    # ---- skills ----
    skills = as_dicts(r.get("skills"))
    if skills:
        heading("Technical Skills")
        rows = []
        for sk in skills:
            items = ", ".join(as_str(i) for i in as_list(sk.get("items")))
            rows.append([Paragraph(fmt(as_str(sk.get("category")) + ":"), st["label"]),
                         Paragraph(fmt(items), st["body"])])
        t = Table(rows, colWidths=[112, CONTENT_W - 112])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
        ]))
        story.append(t)

    # ---- projects ----
    projects = as_dicts(r.get("projects"))
    if projects:
        heading("Projects")
        for p in projects:
            entry_head(p.get("name"), p.get("period"))
            if as_str(p.get("tech")):
                tech = as_str(p.get("tech"))
                story.append(Paragraph(fmt(tech if tech.lower().startswith("tech") else "Tech: " + tech),
                                       st["sub"]))
            bullets(p.get("bullets"))
            story.append(Spacer(1, 2 * s))

    # ---- experience ----
    exp = as_dicts(r.get("experience"))
    if exp:
        titles = [as_str(x.get("title") or x.get("role")) for x in exp]
        all_intern = all("intern" in t.lower() for t in titles)
        heading("Internship Experience" if all_intern else "Experience")
        for x in exp:
            title = x.get("title") or " - ".join(
                v for v in (as_str(x.get("role")), as_str(x.get("company"))) if v)
            entry_head(title, x.get("period"))
            bullets(x.get("bullets"))
            story.append(Spacer(1, 2 * s))

    # ---- achievements / leadership ----
    if as_list(r.get("achievements")):
        heading("Certifications & Achievements")
        bullets(r.get("achievements"))
    if as_list(r.get("leadership")):
        heading("Leadership & Extracurricular")
        bullets(r.get("leadership"))

    return story


def _render(r: dict, s: float) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=MARGIN_Y, bottomMargin=MARGIN_Y,
        title="Resume - " + as_str(r.get("name")), author=as_str(r.get("name")),
    )
    doc.build(build_story(r, s))
    return buf.getvalue()


def build_pdf(resume: dict) -> bytes:
    """Try to fit on one page by shrinking slightly; otherwise allow 2 pages."""
    data = b""
    for scale in (1.0, 0.95, 0.9, 0.86):
        data = _render(resume, scale)
        if len(PdfReader(io.BytesIO(data)).pages) <= 1:
            return data
    return data