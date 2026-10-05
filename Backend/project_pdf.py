"""Project analysis report as a PDF (A4 portrait)."""

import io
from datetime import datetime

from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from pdf_resume import NAVY, as_dicts, as_list, as_str, fmt
from report_pdf import AMBER, GREEN, LINE, MUTED, RED, ZEBRA, hexof, style

MARGIN = 40
W = A4[0] - 2 * MARGIN   # about 515 points

ST = {
    "title": style("p_title", 22, bold=True, color="#1F3A5F", leading=26),
    "sub": style("p_sub", 10.5, color="#555555", leading=14),
    "h2": ParagraphStyle("p_h2", parent=style("p_h2b", 13, bold=True, color="#1F3A5F", leading=16),
                         keepWithNext=1, spaceBefore=12, spaceAfter=5),
    "h2n": ParagraphStyle("p_h2n", parent=style("p_h2nb", 13, bold=True, color="#1F3A5F", leading=16),
                          spaceBefore=12, spaceAfter=5),
    "body": style("p_body", 9.5, leading=12.5),
    "small": style("p_small", 8, color="#666666", leading=10.5),
    "bold": style("p_bold", 10, bold=True, leading=13),
    "q": style("p_q", 10.5, bold=True, color="#111111", leading=13.5),
    "quote": style("p_quote", 8.5, italic=True, color="#555555", leading=11),
    "big": style("p_big", 30, bold=True, color="#1F3A5F", align=TA_CENTER, leading=34),
    "bigl": style("p_bigl", 9, color="#555555", align=TA_CENTER, leading=11),
    "rank": style("p_rank", 12, bold=True, color="#1F3A5F", align=TA_CENTER, leading=15),
    "head": style("p_head", 8.5, bold=True, color="#FFFFFF"),
}

TYPE_TEXT = {
    "tutorial_clone": "Common beginner project",
    "common_idea": "Popular idea",
    "solid_original": "Solid original work",
    "distinctive": "Distinctive idea",
}
VERDICT_TEXT = {"yes": "Shown", "partly": "Partly", "no": "Not shown"}


def num(v) -> str:
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return "0"


def color_for(score) -> str:
    try:
        n = float(score)
    except (TypeError, ValueError):
        return hexof(MUTED)
    return hexof(GREEN if n >= 70 else AMBER if n >= 50 else RED)


def verdict_color(v) -> str:
    return hexof(GREEN if v == "yes" else AMBER if v == "partly" else RED)


def P(text, key="body"):
    return Paragraph(text, ST[key])


def bar(value, width=270, height=9):
    d = Drawing(width, height + 2)
    d.add(Rect(0, 1, width, height, fillColor=HexColor("#E3E8F0"), strokeColor=None))
    v = max(0, min(100, float(value or 0)))
    if v > 0:
        d.add(Rect(0, 1, width * v / 100, height, fillColor=HexColor(color_for(v)), strokeColor=None))
    return d


def bar_table(rows):
    data = []
    for label, value, note in rows:
        data.append([
            P(fmt(label), "bold"), bar(value),
            Paragraph(f'<font color="{color_for(value)}"><b>{fmt(value)}</b></font>', ST["bold"]),
            P(fmt(note), "small"),
        ])
    t = Table(data, colWidths=[130, 250, 34, W - 414])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def summary_boxes(rep):
    overall = rep.get("overall", 0)
    ptype = TYPE_TEXT.get(as_str(rep.get("project_type")), "")
    cells = [
        [Paragraph(f'<font color="{color_for(overall)}">{fmt(overall)}</font>', ST["big"]),
         P("Project score (out of 100)", "bigl")],
        [P(fmt(rep.get("level", "")), "rank"), P("Project level", "bigl")],
        [P(fmt(ptype or "-"), "rank"), P("Project type", "bigl")],
    ]
    t = Table([cells], colWidths=[W * 0.36, W * 0.32, W * 0.32])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), ZEBRA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def checklist_table(items):
    rows = [[P("Checklist item", "head"), P("Result", "head"), P("Points", "head"), P("Evidence from your text", "head")]]
    for it in items:
        v = as_str(it.get("verdict"))
        if it.get("source") == "self":
            evidence = "Self-reported (ticked by you, not checked)."
        elif as_str(it.get("quote")):
            evidence = '"' + as_str(it.get("quote")) + '"'
        else:
            evidence = as_str(it.get("note")) or "-"
        rows.append([
            P(fmt(it.get("label")), "body"),
            Paragraph(f'<font color="{verdict_color(v)}"><b>{VERDICT_TEXT.get(v, v)}</b></font>', ST["body"]),
            P(fmt(f"{num(it.get('points', 0))} / {num(it.get('weight', 0))}"), "body"),
            P(fmt(evidence), "quote"),
        ])
    t = Table(rows, colWidths=[128, 64, 42, W - 234], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), ZEBRA]),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def bullet_list(items, key="body"):
    return [Paragraph("&bull; " + fmt(x), ST[key]) for x in as_list(items)]


def roadmap_block(i, r):
    effort = {"small": "Small (under half a day)", "medium": "Medium (1 to 3 days)", "large": "Large (several days)"}
    gain = r.get("gain") or 0
    meta = "Effort: " + effort.get(as_str(r.get("effort")), "Medium")
    if gain:
        meta += f"  |  Could add about {gain} points"
    parts = [Paragraph(f'<font color="{hexof(NAVY)}"><b>{i}. {fmt(r.get("title"))}</b></font>', ST["bold"]),
             P(fmt(meta), "small")]
    if as_str(r.get("why")):
        parts.append(P(fmt(r.get("why")), "body"))
    for n, h in enumerate(as_list(r.get("how")), 1):
        parts.append(P(fmt(f"Step {n}: {h}"), "body"))
    parts += [Spacer(1, 6)]
    return KeepTogether(parts)


def question_block(i, q, lead=None):
    head = (f'<font color="{hexof(NAVY)}"><b>Question {i}</b></font>  '
            f'<font color="#666666">{fmt(as_str(q.get("category")).title())} | {fmt(as_str(q.get("difficulty")).title())}</font>')
    parts = list(lead or []) + [Paragraph(head, ST["body"]), Spacer(1, 2), P(fmt(q.get("question")), "q"), Spacer(1, 3)]
    kp = as_list(q.get("key_points"))
    if kp:
        parts.append(Paragraph("<b>A good answer covers:</b> " + fmt("; ".join(as_str(k) for k in kp)), ST["body"]))
    if as_str(q.get("sample_answer")):
        t = Table([[P("<b>Sample answer:</b> " + fmt(q.get("sample_answer")), "body")]], colWidths=[W])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ZEBRA), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        parts += [Spacer(1, 4), t]
    parts += [Spacer(1, 8), HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=8)]
    return KeepTogether(parts)


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 18, "Generated by Resume AI. A practice aid: scores do not predict marks or interview results.")
    canvas.drawRightString(A4[0] - MARGIN, 18, f"Page {doc.page}")
    canvas.restoreState()


def build_project_pdf(rep: dict) -> bytes:
    title = as_str(rep.get("title")) or "Project"
    tech = as_str(rep.get("tech"))
    date = datetime.now().strftime("%d %B %Y")

    story = [P("Project Analysis Report", "title"),
             P(fmt("  |  ".join(x for x in (title, tech, date) if x)), "sub"),
             Spacer(1, 4), HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=10),
             summary_boxes(rep), Spacer(1, 8)]

    if as_str(rep.get("level_note")):
        story.append(P(fmt(rep.get("level_note")), "body"))
    if as_str(rep.get("summary")):
        story += [Spacer(1, 4), P(fmt(rep.get("summary")), "body")]
    if as_str(rep.get("project_type_reason")):
        story += [Spacer(1, 3), P(fmt("Project type: " + as_str(rep.get("project_type_reason"))), "small")]
    if rep.get("api_wrapper"):
        story += [Spacer(1, 4), Paragraph(
            f'<font color="{hexof(AMBER)}"><b>Note:</b></font> the text does not show much work of your own beyond '
            "calling ready-made services. Describe what you built or trained yourself, or add such a part.", ST["body"])]

    dims = as_dicts(rep.get("dimensions"))
    if dims:
        story.append(P("Score by area", "h2"))
        story.append(bar_table([(d.get("name"), d.get("score"), f"{num(d.get('points'))} of {num(d.get('max'))} points") for d in dims]))

    items = as_dicts(rep.get("items"))
    if items:
        story += [CondPageBreak(110), P("Checklist with evidence", "h2n"), checklist_table(items)]

    if as_list(rep.get("strengths")):
        story.append(P("What is working", "h2"))
        story += bullet_list(rep.get("strengths"))
    if as_list(rep.get("gaps")):
        story.append(P("What is missing", "h2"))
        story += bullet_list(rep.get("gaps"))

    roadmap = as_dicts(rep.get("roadmap"))
    if roadmap:
        story.append(P("Improvement roadmap (biggest gains first)", "h2"))
        for i, r in enumerate(roadmap, 1):
            story.append(roadmap_block(i, r))

    if as_list(rep.get("look_tips")):
        story.append(P("Make it look professional", "h2"))
        story += bullet_list(rep.get("look_tips"))

    story.append(P("How the score is worked out", "h2"))
    story.append(P(fmt(
        "The project is checked against 15 items in five areas: idea (20 points), technical depth (30), evaluation "
        "and quality (20), delivery (15) and presentation (15). The AI marks each item as shown, partly shown or "
        "not shown, and must quote your own text as proof. The program checks that every quote really appears in what "
        "you wrote; if not, the item gets no credit. Shown = full points, partly = half. Items you ticked yourself "
        "count in half and are labelled self-reported. All scores are calculated by the program, not guessed by the AI. "
        "Levels: Basic below 40, Developing 40 to 59, Strong 60 to 79, Standout 80 and above."), "small"))

    qs = as_dicts(rep.get("questions"))
    for i, q in enumerate(qs, 1):
        lead = [P("Interview questions on this project", "h2"),
                P(fmt("Sample answers use only facts from your text. Parts in [square brackets] need your own real details."),
                  "small"), Spacer(1, 4)] if i == 1 else None
        story.append(question_block(i, q, lead))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN + 6,
                            title="Project Analysis Report", author="Resume AI")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()