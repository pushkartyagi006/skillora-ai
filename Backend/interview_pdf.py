"""Interview practice scorecard as a PDF (A4 portrait)."""

import io
from datetime import datetime

from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
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
    "title": style("i_title", 22, bold=True, color="#1F3A5F", leading=26),
    "sub": style("i_sub", 10.5, color="#555555", leading=14),
    "h2": ParagraphStyle("i_h2", parent=style("i_h2b", 13, bold=True, color="#1F3A5F", leading=16),
                         keepWithNext=1, spaceBefore=12, spaceAfter=5),
    "body": style("i_body", 9.5, leading=12.5),
    "small": style("i_small", 8, color="#666666", leading=10.5),
    "bold": style("i_bold", 10, bold=True, leading=13),
    "q": style("i_q", 10.5, bold=True, color="#111111", leading=13.5),
    "ans": style("i_ans", 9, italic=True, color="#444444", leading=12),
    "big": style("i_big", 30, bold=True, color="#1F3A5F", align=TA_CENTER, leading=34),
    "bigl": style("i_bigl", 9, color="#555555", align=TA_CENTER, leading=11),
    "rank": style("i_rank", 12, bold=True, color="#1F3A5F", align=TA_CENTER, leading=15),
    "foot": style("i_foot", 9, color="#111111", leading=12),
}


def color_for(score) -> str:
    try:
        n = float(score)
    except (TypeError, ValueError):
        return hexof(MUTED)
    return hexof(GREEN if n >= 70 else AMBER if n >= 50 else RED)


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
    """rows: (label, value or None, note)"""
    data = []
    for label, value, note in rows:
        shown = "n/a" if value is None else f"{value}"
        data.append([
            P(fmt(label), "bold"),
            bar(value) if value is not None else P("-", "small"),
            Paragraph(f'<font color="{color_for(value)}"><b>{fmt(shown)}</b></font>', ST["bold"]),
            P(fmt(note), "small"),
        ])
    t = Table(data, colWidths=[110, 280, 34, W - 424])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def summary_boxes(card):
    overall = card.get("overall", 0)
    cells = [
        [Paragraph(f'<font color="{color_for(overall)}">{fmt(overall)}</font>', ST["big"]),
         P("Overall score (out of 100)", "bigl"), P(fmt(card.get("rank", "")), "rank")],
        [P(fmt(f"{card.get('xp', 0)} / {card.get('xp_max', 0)}"), "rank"), P("Points earned", "bigl")],
        [P(fmt(f"{card.get('answered', 0)} of {card.get('total', 0)}"), "rank"), P("Questions answered", "bigl")],
    ]
    t = Table([[cells[0], cells[1], cells[2]]], colWidths=[W * 0.40, W * 0.30, W * 0.30])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), ZEBRA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def question_block(i, q, lead=None):
    score = q.get("overall", 0)
    head = (f'<font color="{hexof(NAVY)}"><b>Question {i}</b></font>  '
            f'<font color="#666666">{fmt(q.get("category_name", q.get("category", "")))}</font>  '
            f'<font color="{color_for(score)}"><b>{fmt(score)}/100</b></font>')
    parts = list(lead or []) + [Paragraph(head, ST["body"]), Spacer(1, 2),
                                P(fmt(q.get("question")), "q"), Spacer(1, 3)]

    if q.get("skipped"):
        parts.append(P("Skipped (no answer given).", "ans"))
    else:
        parts.append(P("Your answer: " + fmt(as_str(q.get("answer")) or "(empty)"), "ans"))
    ex = q.get("examples")
    scores = (f"Content {q.get('content', 0)}  |  Communication {q.get('communication', 0)}  |  "
              f"Examples {'n/a' if ex is None else ex}  |  Time {q.get('seconds', 0)}s")
    parts += [Spacer(1, 3), P(fmt(scores), "small")]

    for s in as_list(q.get("strengths")):
        parts.append(Paragraph(f'<font color="{hexof(GREEN)}"><b>Good:</b></font> {fmt(s)}', ST["body"]))
    for s in as_list(q.get("improvements")):
        parts.append(Paragraph(f'<font color="{hexof(AMBER)}"><b>Improve:</b></font> {fmt(s)}', ST["body"]))
    for s in as_list(q.get("incorrect_claims")):
        parts.append(Paragraph(f'<font color="{hexof(RED)}"><b>Incorrect:</b></font> {fmt(s)}', ST["body"]))
    missed = as_list(q.get("missed_points"))
    if missed and not q.get("skipped"):
        parts.append(Paragraph(f'<b>Missing points:</b> {fmt("; ".join(as_str(m) for m in missed))}', ST["body"]))
    for s in as_list(q.get("comm_tips")):
        parts.append(Paragraph(f'<b>Communication:</b> {fmt(s)}', ST["body"]))
    if as_str(q.get("better_answer")):
        t = Table([[P("<b>Stronger version:</b> " + fmt(q.get("better_answer")), "body")]], colWidths=[W])
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
    canvas.drawString(MARGIN, 18, "Generated by Resume AI. Practice feedback only: scores do not predict real interview results.")
    canvas.drawRightString(A4[0] - MARGIN, 18, f"Page {doc.page}")
    canvas.restoreState()


def build_scorecard_pdf(card: dict) -> bytes:
    name = as_str(card.get("candidate_name"))
    role = as_str(card.get("role")) or "Interview practice"
    company = as_str(card.get("company"))
    headline = role + (f" at {company}" if company else "")
    date = datetime.now().strftime("%d %B %Y")

    story = [P("Interview Practice Scorecard", "title"),
             P(fmt("  |  ".join(x for x in (name, headline, as_str(card.get("difficulty")).title(), date) if x)), "sub"),
             Spacer(1, 4), HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=10),
             summary_boxes(card)]

    dims = card.get("dimensions") if isinstance(card.get("dimensions"), dict) else {}
    story.append(P("Your skills", "h2"))
    story.append(bar_table([
        ("Content", dims.get("content"), "knowledge and key points covered"),
        ("Communication", dims.get("communication"), "length, structure, filler words"),
        ("Examples", dims.get("examples"), "real examples in HR and project answers"),
    ]))

    cats = as_dicts(card.get("categories"))
    if cats:
        story.append(P("Score by round", "h2"))
        story.append(bar_table([(c.get("name"), c.get("score"), f"{c.get('count')} question(s)") for c in cats]))

    badges = as_dicts(card.get("badges"))
    if badges:
        story.append(P("Badges earned", "h2"))
        for b in badges:
            story.append(Paragraph(f'<b>{fmt(b.get("name"))}</b> - {fmt(b.get("description"))}', ST["body"]))

    story.append(P("What to practise next", "h2"))
    for i, tip in enumerate(as_list(card.get("practise")), 1):
        story.append(Paragraph(fmt(f"{i}. {tip}"), ST["body"]))
        story.append(Spacer(1, 2))

    story.append(P("How the score is worked out", "h2"))
    story.append(P(fmt(
        "Each answer scores out of 100. Content = share of the key points your answer clearly covered "
        "(each point needs a quote from your answer), reduced by 15% for each wrong statement (max 30%). "
        "Communication is calculated by program from answer length, structure words, filler words and "
        "ownership ('I' vs 'we'). Examples = 0, 50 or 100 for none, vague or specific. "
        "Answer score = 55% content + 25% communication + 20% examples (70% / 30% when no example is expected). "
        "The overall score is the average of all questions; a skipped question scores 0."), "small"))

    # the heading travels with the first question so it is never left alone at the bottom of a page
    for i, q in enumerate(as_dicts(card.get("questions")), 1):
        lead = [P("Question by question", "h2")] if i == 1 else None
        story.append(question_block(i, q, lead))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN + 6,
                            title="Interview Practice Scorecard", author="Resume AI")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()