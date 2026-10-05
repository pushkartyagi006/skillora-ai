import asyncio
import io
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from pypdf import PdfReader

from builder import call_json, client as ai_client
from scoring import _has, compute_scores, extract_skills

router = APIRouter(prefix="/api/company")

MAX_FILES = 50
MAX_BYTES = 5 * 1024 * 1024
TOP_AI = 5

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CGPA_RE = re.compile(r"(?:cgpa|gpa)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?", re.I)

AI_PROMPT = """You are helping a recruiter read a shortlist.
For each candidate below, write ONE plain sentence (maximum 25 words) saying why they
fit the job or what is missing. Use only the data given. Do not invent facts and do not
change or restate scores.
Reply with ONLY valid JSON: {"summaries": [{"id": 0, "text": "..."}]}

JOB DESCRIPTION:
<<JD>>

CANDIDATES:
<<DATA>>
"""


def pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def find_cgpa(text: str):
    m = CGPA_RE.search(text)
    if not m:
        return None
    value = float(m.group(1))
    scale = float(m.group(2)) if m.group(2) else 10.0
    if scale <= 0:
        return None
    cgpa = round(value / scale * 10, 2)
    return cgpa if 0 <= cgpa <= 10 else None


def guess_name(text: str, filename: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if 2 <= len(line) <= 40 and not re.search(r"[\d@:/|]", line):
            return line.title() if line.isupper() else line
        break
    return Path(filename).stem.replace("_", " ").replace("-", " ")


def meets(term: str, resume_lower: str, resume_skills: set) -> bool:
    """Does the resume have this must-have skill? Known skills use the skill list
    (with aliases); unknown ones fall back to a plain word search."""
    known = extract_skills(term)
    if known:
        return known <= resume_skills
    return _has(resume_lower, term.strip().lower())


def evaluate(items, jd: str, must_have: str, min_score: int, min_cgpa: float) -> dict:
    jd_skills = sorted(extract_skills(jd))
    must = [m.strip() for m in re.split(r"[,\n;]", must_have) if m.strip()]
    candidates, unreadable = [], []

    for filename, data in items:
        try:
            text = pdf_to_text(data)
        except Exception:
            text = ""
        if len(text.strip()) < 50:
            unreadable.append({"filename": filename,
                               "reason": "Could not read text (scanned image or damaged PDF)"})
            continue

        sc = compute_scores(text, jd)
        resume_skills = extract_skills(text)
        lower = text.lower()
        reasons, flags = [], []

        missing_must = [m for m in must if not meets(m, lower, resume_skills)]
        if missing_must:
            reasons.append("Missing must-have: " + ", ".join(missing_must))
        if sc["overall"] < min_score:
            reasons.append(f"Score {sc['overall']} is below the minimum {min_score}")

        cgpa = find_cgpa(text)
        if min_cgpa > 0:
            if cgpa is None:
                flags.append("CGPA not found - check manually")
            elif cgpa < min_cgpa:
                reasons.append(f"CGPA {cgpa:g} is below the minimum {min_cgpa:g}")

        email = EMAIL_RE.search(text)
        candidates.append({
            "filename": filename,
            "name": guess_name(text, filename),
            "email": email.group(0) if email else "",
            "cgpa": cgpa,
            "overall": sc["overall"],
            "fit": sc["breakdown"]["fit"]["score"],
            "strength": sc["strength"],
            "matched_skills": sc["matched_skills"],
            "missing_skills": sc["missing_skills"],
            "selected": not reasons,
            "reasons": reasons,
            "flags": flags,
            "rank": None,
            "ai_summary": "",
        })

    candidates.sort(key=lambda c: (not c["selected"], -c["overall"], -c["fit"], -c["strength"]))
    rank = 0
    for c in candidates:
        if c["selected"]:
            rank += 1
            c["rank"] = rank

    warning = ""
    if not jd_skills and not must:
        warning = ("No known technical skills were found in the job description, so ranking relies on "
                   "keyword overlap (approximate). Add must-have skills for a stricter filter.")

    return {"candidates": candidates, "unreadable": unreadable,
            "jd_skills": jd_skills, "warning": warning}


@router.post("/rank")
async def rank_resumes(
    job_description: str = Form(...),
    must_have: str = Form(""),
    min_score: int = Form(50),
    min_cgpa: float = Form(0),
    files: list[UploadFile] = File(...),
):
    if not job_description.strip():
        return {"error": "Paste a job description first."}
    if not files:
        return {"error": "Upload at least one resume."}
    if len(files) > MAX_FILES:
        return {"error": f"Please upload at most {MAX_FILES} resumes at a time."}

    items, skipped = [], []
    for f in files:
        name = f.filename or "resume.pdf"
        if not name.lower().endswith(".pdf"):
            skipped.append({"filename": name, "reason": "Not a PDF file"})
            continue
        data = await f.read()
        if len(data) > MAX_BYTES:
            skipped.append({"filename": name, "reason": "File is larger than 5 MB"})
            continue
        items.append((name, data))

    result = await asyncio.to_thread(
        evaluate, items, job_description, must_have, min_score, min_cgpa)
    result["unreadable"] = skipped + result["unreadable"]

    chosen = [c for c in result["candidates"] if c["selected"]]
    result["summary"] = {
        "total": len(files),
        "shortlisted": len(chosen),
        "not_shortlisted": len(result["candidates"]) - len(chosen),
        "unreadable": len(result["unreadable"]),
    }

    # One AI call for the top few: scores and skill lists only, never resume text.
    result["ai_note"] = ""
    top = chosen[:TOP_AI]
    if top and ai_client is not None:
        payload = [
            {"id": i, "overall": c["overall"], "job_fit": c["fit"],
             "matched_skills": c["matched_skills"], "missing_skills": c["missing_skills"],
             "flags": c["flags"]}
            for i, c in enumerate(top)
        ]
        import json
        prompt = (AI_PROMPT.replace("<<JD>>", job_description[:3000])
                  .replace("<<DATA>>", json.dumps(payload)))
        try:
            out = await asyncio.to_thread(call_json, prompt)
            for item in (out.get("summaries", []) if isinstance(out, dict) else []):
                i = item.get("id") if isinstance(item, dict) else None
                if isinstance(i, int) and 0 <= i < len(top):
                    top[i]["ai_summary"] = str(item.get("text", "")).strip()
        except Exception:
            result["ai_note"] = "AI one-line reasons are unavailable right now. The ranking is not affected."

    return result