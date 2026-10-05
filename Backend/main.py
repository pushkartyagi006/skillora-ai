import asyncio
import io
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pypdf import PdfReader

from builder import router as builder_router
from ranking import router as company_router
from report_pdf import router as report_router
from scoring import compute_scores
from teacher import router as teacher_router
from interview import router as interview_router
from project import router as project_router
from auth import router as auth_router
from check_pdf import router as check_router

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACKS = [
    m.strip()
    for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-3.1-flash-lite").split(",")
    if m.strip()
]
client = genai.Client(api_key=API_KEY) if API_KEY else None

app = FastAPI(title="Resume AI")
app.include_router(builder_router)
app.include_router(company_router)
app.include_router(report_router)
app.include_router(teacher_router)
app.include_router(interview_router)
app.include_router(project_router)
app.include_router(auth_router)
app.include_router(check_router)
FRONTEND_DIR = BASE_DIR.parent / "frontend"

PROMPT = """You are an expert resume reviewer for the Indian tech job market.
A scoring program has ALREADY computed the numbers below. Do not change them
or invent other scores. Explain them and help the candidate improve.

COMPUTED SCORES (0-100): <<SCORES>>
MATCHED SKILLS: <<MATCHED>>
MISSING SKILLS: <<MISSING>>

Reply with ONLY valid JSON in exactly this shape:
{
  "match_summary": "2-3 sentence assessment that agrees with the scores above",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "suggestions": ["specific, actionable improvements; address the missing skills and low-scoring parts"]
}
Rules: use only information present in the resume and job description.
Never invent experience or skills the candidate does not have.

JOB DESCRIPTION:
<<JD>>

RESUME:
<<RESUME>>
"""


def pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def call_ai(prompt: str) -> dict:
    """Try the main model, retry on busy errors, then fall back to other models."""
    last_error = "unknown error"
    for model in [MODEL] + FALLBACKS:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                )
                data = json.loads(response.text)
                data["model_used"] = model
                return data
            except json.JSONDecodeError:
                last_error = "AI returned an invalid answer."
                continue
            except Exception as e:
                last_error = str(e)
                busy = any(x in last_error for x in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))
                if busy:
                    time.sleep(2 * (attempt + 1))
                    continue
                break  # e.g. 404 model not found: go to the next model
    raise RuntimeError(last_error)


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_configured": client is not None, "model": MODEL, "fallbacks": FALLBACKS}


@app.get("/api/models")
def list_models():
    if client is None:
        return {"error": "GEMINI_API_KEY missing. Check backend/.env"}
    return {"models": [m.name for m in client.models.list()]}


@app.post("/api/extract")
async def extract_text(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Please upload a PDF file."}
    text = pdf_to_text(await file.read())
    return {"filename": file.filename, "characters": len(text), "text": text}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), job_description: str = Form(...)):
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Please upload a PDF file."}

    resume_text = pdf_to_text(await file.read())
    if len(resume_text.strip()) < 50:
        return {"error": "Could not read text from this PDF (it may be scanned)."}

    # 1) scores computed by plain code (same input -> same output)
    scores = compute_scores(resume_text, job_description)
    result = {"scores": scores}

    # 2) AI explanation (if the AI fails, scores are still returned)
    if client is None:
        result["ai_error"] = "GEMINI_API_KEY missing. Check backend/.env and restart the server."
        return result

    score_summary = {k: v["score"] for k, v in scores["breakdown"].items()}
    score_summary["overall"] = scores["overall"]

    prompt = (
        PROMPT.replace("<<SCORES>>", json.dumps(score_summary))
        .replace("<<MATCHED>>", ", ".join(scores["matched_skills"]) or "none")
        .replace("<<MISSING>>", ", ".join(scores["missing_skills"]) or "none")
        .replace("<<JD>>", job_description)
        .replace("<<RESUME>>", resume_text)
    )

    try:
        ai = await asyncio.to_thread(call_ai, prompt)
        result.update(ai)
    except Exception as e:
        result["ai_error"] = (
            "The AI is busy or unavailable right now, so only the computed scores are shown. "
            f"Wait a minute and click Analyze again. Details: {e}"
        )

    return result


# Keep this LAST so the API routes above take priority
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")