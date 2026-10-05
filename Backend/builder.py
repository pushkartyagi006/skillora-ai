import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from google import genai
from google.genai import types
from pydantic import BaseModel

from pdf_resume import build_pdf

load_dotenv(Path(__file__).resolve().parent / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACKS = [
    m.strip()
    for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-3.1-flash-lite").split(",")
    if m.strip()
]
client = genai.Client(api_key=API_KEY) if API_KEY else None

router = APIRouter(prefix="/api/builder")


class Profile(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: str = ""
    target_role: str = ""
    job_description: str = ""
    education: str = ""
    skills: str = ""
    projects: str = ""
    experience: str = ""
    achievements: str = ""
    leadership: str = ""


class QA(BaseModel):
    question: str
    answer: str = ""


class GenerateIn(BaseModel):
    profile: Profile
    answers: list[QA] = []


class ReviseIn(BaseModel):
    resume: dict
    instruction: str


class PdfIn(BaseModel):
    resume: dict


QUESTIONS_PROMPT = """You are a resume coach for Indian engineering students.
Read the candidate details below and ask exactly 5 specific follow-up questions
that would let you write stronger resume bullets: measurable results, tools used,
the candidate's own contribution, scale (users, data size, team size), and impact.
Do not ask for information that is already given. Keep each question short.
Reply with ONLY valid JSON: {"questions": ["...", "...", "...", "...", "..."]}

CANDIDATE DETAILS:
<<PROFILE>>
"""

SHAPE = """{
  "name": "",
  "title": "target role headline, e.g. Aspiring Software Developer",
  "contact": {"phone": "", "email": "", "location": "", "links": ["linkedin...", "github..."]},
  "summary": "2-3 sentences",
  "education": [{"title": "degree or class", "period": "2023 - 2027 (Expected)",
                 "subtitle": "Institution, City | CGPA or percentage", "note": "optional, e.g. Relevant Coursework: ..."}],
  "skills": [{"category": "Languages", "items": ["Python"]}],
  "projects": [{"name": "Project - short type", "period": "Jan 2026 - Apr 2026",
                "tech": "tools used | GitHub link if given", "bullets": ["..."]}],
  "experience": [{"title": "Role - Company", "period": "May 2026 - Jul 2026", "bullets": ["..."]}],
  "achievements": ["certifications, awards, coding profile results"],
  "leadership": ["club roles, volunteering, open source"]
}"""

GENERATE_PROMPT = """You are an expert resume writer for the Indian tech job market.
Write an ATS-friendly one-page resume from the candidate details and answers below.
Reply with ONLY valid JSON in exactly this shape (use empty lists or empty strings
when there is no data; empty sections are left out of the PDF):
<<SHAPE>>

STRICT RULES:
- Use ONLY information in the details and answers. Never invent employers, dates,
  numbers, skills, or results. If a number was not given, write the bullet without one.
- Start every bullet with a strong action verb; keep each bullet to one or two lines.
- Plain text only: no markdown, no HTML, no special symbols.
- If a target role or job description is given, order and word things to fit it,
  but never add skills the candidate did not mention.

CANDIDATE DETAILS:
<<PROFILE>>

FOLLOW-UP ANSWERS:
<<ANSWERS>>
"""

REVISE_PROMPT = """You are editing a resume that is stored as JSON.
Apply the candidate's change request to the CURRENT RESUME and return the full updated resume.
Reply with ONLY valid JSON in exactly this shape:
{"message": "one or two short sentences saying what you changed, or why you could not",
 "resume": <the complete updated resume, same shape as the current resume>}

The resume shape is:
<<SHAPE>>

STRICT RULES:
- Change only what the request asks for; keep everything else exactly as it is.
- Facts the candidate states in the change request may be used. Never add any other
  employer, date, number, skill, or result that is not already in the resume or the request.
- If the request needs information you do not have, do not make it up: leave the resume
  unchanged and use "message" to say what information is needed.
- Plain text only: no markdown, no HTML, no special symbols.
- Keep the resume to one page: if you add content, keep it short.

CURRENT RESUME:
<<RESUME>>

CHANGE REQUEST:
<<INSTRUCTION>>
"""


def profile_text(p: Profile) -> str:
    lines = []
    for key, value in p.model_dump().items():
        if value.strip():
            lines.append(f"{key.replace('_', ' ').title()}: {value.strip()}")
    return "\n".join(lines)


def call_json(prompt: str) -> dict:
    last_error = "unknown error"
    for model in [MODEL] + FALLBACKS:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.3,
                    ),
                )
                return json.loads(response.text)
            except json.JSONDecodeError:
                last_error = "AI returned an invalid answer."
            except Exception as e:
                last_error = str(e)
                if any(x in last_error for x in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                    time.sleep(2 * (attempt + 1))
                    continue
                break
    raise RuntimeError(last_error)


@router.post("/questions")
async def questions(p: Profile):
    if client is None:
        return {"error": "GEMINI_API_KEY missing. Check backend/.env and restart the server."}
    prompt = QUESTIONS_PROMPT.replace("<<PROFILE>>", profile_text(p))
    try:
        data = await asyncio.to_thread(call_json, prompt)
    except Exception as e:
        return {"error": f"AI call failed: {e}"}
    qs = data.get("questions", []) if isinstance(data, dict) else []
    return {"questions": [str(q) for q in qs][:6]}


@router.post("/generate")
async def generate(body: GenerateIn):
    if client is None:
        return {"error": "GEMINI_API_KEY missing. Check backend/.env and restart the server."}
    answers = "\n".join(
        f"Q: {a.question}\nA: {a.answer.strip()}" for a in body.answers if a.answer.strip()
    ) or "none"
    prompt = (
        GENERATE_PROMPT.replace("<<SHAPE>>", SHAPE)
        .replace("<<PROFILE>>", profile_text(body.profile))
        .replace("<<ANSWERS>>", answers)
    )
    try:
        data = await asyncio.to_thread(call_json, prompt)
    except Exception as e:
        return {"error": f"AI call failed: {e}"}
    if not isinstance(data, dict):
        return {"error": "AI returned an invalid answer. Please try again."}
    return {"resume": data}


@router.post("/revise")
async def revise(body: ReviseIn):
    if client is None:
        return {"error": "GEMINI_API_KEY missing. Check backend/.env and restart the server."}
    if not body.instruction.strip():
        return {"error": "Tell the AI what to change."}
    prompt = (
        REVISE_PROMPT.replace("<<SHAPE>>", SHAPE)
        .replace("<<RESUME>>", json.dumps(body.resume, ensure_ascii=False))
        .replace("<<INSTRUCTION>>", body.instruction.strip())
    )
    try:
        data = await asyncio.to_thread(call_json, prompt)
    except Exception as e:
        return {"error": f"AI call failed: {e}"}
    if not isinstance(data, dict) or not isinstance(data.get("resume"), dict):
        return {"error": "AI returned an invalid answer. Please try again."}
    return {"resume": data["resume"], "message": str(data.get("message", "")).strip()}


@router.post("/pdf")
async def pdf(body: PdfIn):
    try:
        data = await asyncio.to_thread(build_pdf, body.resume)
    except Exception as e:
        return JSONResponse({"error": f"Could not build the PDF: {e}"}, status_code=500)
    return Response(content=data, media_type="application/pdf")