import asyncio
import io
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from pypdf import PdfReader

from builder import call_json, client as ai_client
from ranking import meets
from scoring import extract_skills
from teacher_pdf import build_teacher_report

router = APIRouter(prefix="/api/teacher")

MAX_FILES = 30
MAX_BYTES = 15 * 1024 * 1024
AI_CONCURRENCY = 3
FULL_TEXT_LIMIT = 24000
MIN_READABLE_CHARS = 200

# Common section names and the other headings that count as the same section.
SECTION_ALIASES = {
    "abstract": ["abstract"],
    "introduction": ["introduction"],
    "literature review": ["literature review", "literature survey", "related work", "review of literature"],
    "problem statement": ["problem statement", "problem definition"],
    "objectives": ["objectives", "objective", "aims and objectives"],
    "methodology": ["methodology", "methods", "research methodology", "proposed methodology"],
    "implementation": ["implementation"],
    "results": ["results", "result analysis", "results and discussion"],
    "testing": ["testing", "test cases"],
    "conclusion": ["conclusion", "conclusions"],
    "future scope": ["future scope", "future work", "future enhancements", "future enhancement"],
    "references": ["references", "bibliography"],
    "acknowledgement": ["acknowledgement", "acknowledgment", "acknowledgements", "acknowledgments"],
    "table of contents": ["table of contents", "contents"],
    "certificate": ["certificate"],
    "declaration": ["declaration"],
}

NUM_PREFIX = re.compile(
    r"^(?:chapter\s+[\divxlc]+\s*[:.\-]?\s*|\d+(?:\.\d+)*\s*[.):\-]?\s*|[ivxlc]+\s*[.)]\s+)", re.I)
NAME_RE = re.compile(
    r"(?:submitted\s+by|student\s*name|name\s+of\s+(?:the\s+)?student|candidate\s*name)\s*[:\-]\s*"
    r"([A-Za-z][A-Za-z .'-]{2,40})", re.I)
ROLL_RE = re.compile(
    r"(?:university\s+roll\s*(?:no\.?|number)|roll\s*(?:no\.?|number)|enrol+ment\s*(?:no\.?|number)|"
    r"registration\s*(?:no\.?|number)|reg\.?\s*no\.?)\s*[:\-]?\s*([A-Za-z0-9/\-]{4,20})", re.I)

AI_PROMPT = """You are helping a teacher check a student project report against the teacher's own requirements.
For EACH numbered requirement decide whether the report text clearly satisfies it.
Verdicts:
- "met": the report clearly shows it. You MUST copy a short EXACT quote (at most 20 words) from the report text as evidence.
- "not_met": <<NOTMET>>
- "unclear": you cannot tell from the text given.
Never guess. Never invent a quote. Judge only from the report text below.
Reply with ONLY valid JSON:
{"results": [{"id": 0, "verdict": "met", "evidence": "exact quote or empty", "reason": "one short sentence"}]}

REQUIREMENTS:
<<REQS>>

REPORT TEXT:
<<TEXT>>
"""


# ---------------------------------------------------------------- helpers
def split_items(text: str, newline_only: bool = False) -> list:
    pattern = r"\n+" if newline_only else r"[,;\n]+"
    seen, out = set(), []
    for s in re.split(pattern, text or ""):
        s = s.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def read_pdf(data: bytes):
    reader = PdfReader(io.BytesIO(data))
    pages = len(reader.pages)
    parts = []
    for p in reader.pages:
        try:
            parts.append(p.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n".join(parts), pages


def guess_student(text: str, filename: str):
    head = text[:3000]
    name, roll = "", ""
    m = NAME_RE.search(head)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip(" .-")
    m = ROLL_RE.search(head)
    if m:
        roll = m.group(1).strip("-/")
    if len(name) < 3 or len(name.split()) > 5:
        name = Path(filename).stem.replace("_", " ").replace("-", " ")
    return name, roll


def section_aliases(term: str) -> list:
    t = re.sub(r"\s+", " ", term.strip().lower())
    for key, aliases in SECTION_ALIASES.items():
        if t == key or t in aliases:
            return aliases
    return [t]


def headings_of(text: str) -> list:
    """Short lines that look like headings: (normalised text, looks_like_a_sentence)."""
    out = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or len(raw) > 90:
            continue
        line = NUM_PREFIX.sub("", raw).strip().lower()
        if not line:
            continue
        if re.search(r"\.{3,}|\s\d+\s*$", line):   # table-of-contents lines
            continue
        line = line.strip(" :.-\t")
        toks = line.split()
        if len(toks) >= 4 and all(len(t) == 1 for t in toks):   # "a b s t r a c t"
            line = "".join(toks)
        if not line:
            continue
        sentence_like = raw.endswith((".", ",")) and len(line.split()) > 2
        out.append((line, sentence_like))
    return out


def has_section(headings: list, aliases: list) -> bool:
    for line, sentence_like in headings:
        words = line.split()
        for a in aliases:
            if line == a:
                return True
            if (line.startswith(a + " ") and not sentence_like
                    and len(words) <= len(a.split()) + 3):
                return True
    return False


def add(rec: dict, kind: str, label: str, result: str, detail: str = ""):
    rec["checks"].append({"kind": kind, "label": label, "result": result, "detail": detail})


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").lower().strip()


# ------------------------------------------------------- checks without AI
def check_static(filename: str, data: bytes, cfg: dict) -> dict:
    rec = {"filename": filename, "name": "", "roll_no": "", "pages": 0, "checks": [],
           "notes": [], "status": "approved", "_text": ""}
    try:
        text, pages = read_pdf(data)
    except Exception:
        text, pages = "", 0
        rec["notes"].append("Could not open this PDF (damaged or password-protected). Check it manually.")
    rec["pages"] = pages
    rec["name"], rec["roll_no"] = guess_student(text, filename)

    if cfg["min_pages"] > 0 and pages:
        label = f"At least {cfg['min_pages']} pages"
        if pages >= cfg["min_pages"]:
            add(rec, "pages", label, "pass", f"{pages} pages")
        else:
            add(rec, "pages", label, "fail", f"only {pages} pages")

    if len(text.strip()) < MIN_READABLE_CHARS:
        if not rec["notes"]:
            rec["notes"].append("Could not read the text (probably scanned images). Check this report manually.")
        return rec

    headings = headings_of(text)
    for s in cfg["sections"]:
        found = has_section(headings, section_aliases(s))
        add(rec, "section", f"{s} section", "pass" if found else "fail",
            "" if found else "no heading with this name found")

    lower = text.lower()
    skills = extract_skills(text)
    for k in cfg["keywords"]:
        ok = meets(k, lower, skills)
        add(rec, "keyword", f"Mentions {k}", "pass" if ok else "fail",
            "" if ok else "not found in the report")

    rec["_text"] = text
    return rec


def check_all(items, cfg):
    return [check_static(name, data, cfg) for name, data in items]


# --------------------------------------------------------------- AI checks
def prepare_text(text: str):
    if len(text) <= FULL_TEXT_LIMIT:
        return text, False
    mid = len(text) // 2
    short = text[:12000] + "\n[...]\n" + text[mid - 3000: mid + 3000] + "\n[...]\n" + text[-6000:]
    return short, True


async def run_ai(rec: dict, reqs: list, sem: asyncio.Semaphore) -> bool:
    """Checks the teacher's free-text requirements. Returns False if the AI failed."""
    text = rec["_text"]
    shown, shortened = prepare_text(text)
    notmet = ('use "unclear" instead, because the text below is shortened and the answer may be in a missing part'
              if shortened else
              "the report text is complete and clearly does not satisfy it; give a short reason")
    prompt = (AI_PROMPT.replace("<<NOTMET>>", notmet)
              .replace("<<REQS>>", "\n".join(f"{i}: {r}" for i, r in enumerate(reqs)))
              .replace("<<TEXT>>", shown))
    data, ok = None, True
    async with sem:
        try:
            data = await asyncio.to_thread(call_json, prompt)
        except Exception:
            ok = False

    by_id = {}
    if isinstance(data, dict):
        for item in data.get("results", []) if isinstance(data.get("results"), list) else []:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                by_id[item["id"]] = item

    full_norm = norm(text)
    for i, req in enumerate(reqs):
        item = by_id.get(i) or {}
        verdict = str(item.get("verdict", "")).lower()
        evidence = str(item.get("evidence", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if verdict == "met" and evidence and norm(evidence) in full_norm:
            add(rec, "ai", req, "pass", evidence)
        elif verdict == "met":
            add(rec, "ai", req, "unclear", "the AI could not show proof from the report text")
        elif verdict == "not_met" and not shortened:
            add(rec, "ai", req, "fail", reason or "not found in the report")
        else:
            add(rec, "ai", req, "unclear", reason or "the AI could not tell from the report text")
    return ok


def finalize(rec: dict) -> dict:
    results = [c["result"] for c in rec["checks"]]
    if "fail" in results:
        rec["status"] = "unapproved"
    elif "unclear" in results or rec["notes"]:
        rec["status"] = "review"
    else:
        rec["status"] = "approved"
    rec.pop("_text", None)
    return rec


# ------------------------------------------------------------------ routes
@router.post("/check")
async def check_reports(
    assignment: str = Form(""),
    min_pages: int = Form(0),
    sections: str = Form(""),
    keywords: str = Form(""),
    ai_requirements: str = Form(""),
    files: list[UploadFile] = File(...),
):
    cfg = {
        "min_pages": max(0, min_pages),
        "sections": split_items(sections),
        "keywords": split_items(keywords),
        "ai_reqs": split_items(ai_requirements, newline_only=True),
    }
    if not (cfg["min_pages"] > 0 or cfg["sections"] or cfg["keywords"] or cfg["ai_reqs"]):
        return {"error": "Add at least one requirement first."}
    if not files:
        return {"error": "Upload at least one report."}
    if len(files) > MAX_FILES:
        return {"error": f"Please upload at most {MAX_FILES} reports at a time."}

    items, skipped = [], []
    for f in files:
        name = f.filename or "report.pdf"
        data = await f.read()
        if not name.lower().endswith(".pdf"):
            problem = "Not a PDF file."
        elif len(data) > MAX_BYTES:
            problem = "File is larger than 15 MB."
        else:
            items.append((name, data))
            continue
        skipped.append({"filename": name, "name": Path(name).stem, "roll_no": "", "pages": 0,
                        "checks": [], "notes": [problem + " Check it manually."], "status": "review"})

    records = await asyncio.to_thread(check_all, items, cfg)

    ai_note = ""
    if cfg["ai_reqs"]:
        pending = [r for r in records if r["_text"] and not any(c["result"] == "fail" for c in r["checks"])]
        for r in records:
            if r["_text"] and r not in pending:
                r["notes"].append("The AI requirements were not checked because this report already failed another requirement.")
        if ai_client is None:
            for r in pending:
                for req in cfg["ai_reqs"]:
                    add(r, "ai", req, "unclear", "AI is not configured (check GEMINI_API_KEY)")
            ai_note = "The AI is not configured, so AI requirements could not be checked."
        else:
            sem = asyncio.Semaphore(AI_CONCURRENCY)
            outcomes = await asyncio.gather(*(run_ai(r, cfg["ai_reqs"], sem) for r in pending))
            if not all(outcomes):
                ai_note = ("The AI was busy or unavailable for some reports. Those are listed under "
                           "Needs manual review. Wait a minute and run the check again.")

    reports = [finalize(r) for r in records] + skipped
    order = {"approved": 0, "unapproved": 1, "review": 2}
    reports.sort(key=lambda r: (order[r["status"]], r["name"].lower()))

    return {
        "reports": reports,
        "summary": {
            "total": len(files),
            "approved": sum(r["status"] == "approved" for r in reports),
            "unapproved": sum(r["status"] == "unapproved" for r in reports),
            "review": sum(r["status"] == "review" for r in reports),
        },
        "requirements": {
            "assignment": assignment.strip(),
            "min_pages": cfg["min_pages"],
            "sections": cfg["sections"],
            "keywords": cfg["keywords"],
            "ai_requirements": cfg["ai_reqs"],
        },
        "ai_note": ai_note,
    }


class ReportIn(BaseModel):
    result: dict


@router.post("/report")
async def teacher_report(body: ReportIn):
    try:
        data = await asyncio.to_thread(build_teacher_report, body.result)
    except Exception as e:
        return JSONResponse({"error": f"Could not build the report: {e}"}, status_code=500)
    return Response(content=data, media_type="application/pdf")