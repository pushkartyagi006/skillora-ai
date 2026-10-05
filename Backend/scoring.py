import re

# canonical skill -> words that count as that skill
SKILLS = {
    "python": ["python"],
    "java": ["java"],
    "c++": ["c++", "cpp"],
    "c#": ["c#"],
    "javascript": ["javascript", "js", "es6"],
    "typescript": ["typescript"],
    "sql": ["sql"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    "react": ["react", "react.js", "reactjs"],
    "node.js": ["node.js", "nodejs", "node"],
    "express": ["express.js", "expressjs"],
    "flask": ["flask"],
    "django": ["django"],
    "fastapi": ["fastapi"],
    "spring boot": ["spring boot", "springboot", "spring framework"],
    "rest api": ["rest api", "rest apis", "restful", "restful api", "rest services"],
    "mysql": ["mysql"],
    "postgresql": ["postgresql", "postgres"],
    "mongodb": ["mongodb", "mongo"],
    "git": ["git", "github", "gitlab"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "ci/cd": ["ci/cd", "cicd", "github actions", "jenkins"],
    "linux": ["linux"],
    "dsa": ["dsa", "data structures", "algorithms"],
    "oop": ["oop", "object oriented", "object-oriented"],
    "dbms": ["dbms"],
    "operating systems": ["operating systems"],
    "system design": ["system design"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"],
    "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "data analysis": ["data analysis", "data analytics"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "excel": ["excel"],
    "unit testing": ["unit test", "unit tests", "unit testing", "jest", "pytest", "junit"],
    "agile": ["agile", "scrum"],
    "jira": ["jira"],
    "postman": ["postman"],
    "problem solving": ["problem solving", "problem-solving"],
    "teamwork": ["teamwork", "team player", "collaboration", "collaborated", "collaborative"],
    "communication": ["communication", "communicate"],
}

# having one skill also proves another
IMPLIES = {
    "mysql": "sql",
    "postgresql": "sql",
}

WEIGHTS = {"skills": 50, "experience": 20, "education": 10, "quality": 20}

ACTION_VERBS = (
    "built|developed|designed|implemented|created|deployed|integrated|optimized|"
    "optimised|reduced|improved|led|automated|trained|wrote|engineered|launched|"
    "architected|migrated|organised|organized|raised|increased"
)


def _has(text: str, alias: str) -> bool:
    pattern = r"(?<![a-z0-9+#.])" + re.escape(alias) + r"(?![a-z0-9+#])"
    return re.search(pattern, text) is not None


def extract_skills(text: str) -> set:
    t = text.lower()
    found = {skill for skill, aliases in SKILLS.items() if any(_has(t, a) for a in aliases)}
    for skill in list(found):
        if skill in IMPLIES:
            found.add(IMPLIES[skill])
    return found


def _clean_lines(text: str):
    for line in text.splitlines():
        line = re.sub(r"^[^A-Za-z0-9]+", "", line.strip())
        if line:
            yield line


def score_experience(text: str):
    t = text.lower()
    score, notes = 0, []

    if re.search(r"\bintern(ship)?\b|\bwork experience\b|\bemployment\b|\bfull[- ]time\b", t):
        score += 40
        notes.append("internship/work experience found (+40)")
    else:
        notes.append("no internship or work experience found")

    action_lines = [l for l in _clean_lines(text) if re.match(rf"({ACTION_VERBS})\b", l.lower())]
    pts = min(40, len(action_lines) * 8)
    score += pts
    notes.append(f"{len(action_lines)} achievement bullets starting with action verbs (+{pts})")

    numeric = [l for l in _clean_lines(text) if re.search(r"\d+\s*%|\d+\+|\b\d{2,}\b", l)]
    pts = min(20, len(numeric) * 4)
    score += pts
    notes.append(f"{len(numeric)} lines with numbers/results (+{pts})")

    return min(score, 100), "; ".join(notes)


def score_education(text: str):
    t = text.lower()
    score, notes = 0, []

    if re.search(r"\bb\.?\s?tech\b|\bbachelor|\bm\.?\s?tech\b|\bmaster|\bbca\b|\bmca\b|\bb\.e\b|\bb\.?\s?sc\b", t):
        score += 50
        notes.append("degree found (+50)")
    else:
        notes.append("degree not found")

    m = re.search(r"(?:cgpa|gpa)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?", t)
    if m:
        value = float(m.group(1))
        scale = float(m.group(2)) if m.group(2) else 10.0
        ratio = value / scale if scale else 0
        pts = 50 if ratio >= 0.8 else 35 if ratio >= 0.7 else 20 if ratio >= 0.6 else 10
        score += pts
        notes.append(f"CGPA {value:g}/{scale:g} (+{pts})")
    else:
        score += 20
        notes.append("CGPA not found (neutral +20)")

    return min(score, 100), "; ".join(notes)


def score_quality(text: str):
    t = text.lower()
    score, notes = 0, []

    contact = {
        "email": r"[\w.+-]+@[\w-]+\.[\w.]+",
        "phone": r"(\+?\d[\d\s-]{8,}\d)",
        "linkedin": r"linkedin\.com",
        "github": r"github\.com",
    }
    missing = []
    for name, pat in contact.items():
        if re.search(pat, t):
            score += 10
        else:
            missing.append(name)
    notes.append("contact details complete (+40)" if not missing else f"missing contact: {', '.join(missing)}")

    sections = {
        "education": r"education",
        "skills": r"skills",
        "projects": r"projects?",
        "experience": r"experience|internship",
        "summary": r"summary|objective|profile",
    }
    absent = []
    for name, pat in sections.items():
        if re.search(pat, t):
            score += 6
        else:
            absent.append(name)
    notes.append("all standard sections present (+30)" if not absent else f"missing sections: {', '.join(absent)}")

    n = len(text.strip())
    if 1500 <= n <= 7000:
        score += 15
        notes.append("good length (+15)")
    else:
        score += 5
        notes.append("length looks too short or too long (+5)")

    numeric = sum(1 for l in _clean_lines(text) if re.search(r"\d+\s*%|\d+\+", l))
    if numeric >= 3:
        score += 15
        notes.append("achievements are quantified (+15)")
    else:
        score += 5
        notes.append("few quantified achievements (+5)")

    return min(score, 100), "; ".join(notes)


SOFT_SKILLS = {"problem solving", "teamwork", "communication"}
SOFT_WEIGHT = 0.3

STOPWORDS = set("""
the and for with that this from will have has had are was were been being you your our their
they them but not can should must may also such than then into over under about across per
etc job role position candidate candidates company looking seeking required requirements
preferred plus good strong excellent ability able work working works experience experienced
years year skills skill knowledge understanding team teams including include includes using
use used develop developing development responsibilities responsible duties qualification
qualifications education degree bachelor master related relevant more other any all new
need needs want wanted must have should would could well best great high highly based
""".split())


def _skill_weight(skill: str) -> float:
    return SOFT_WEIGHT if skill in SOFT_SKILLS else 1.0


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z+#]{3,}", text.lower()) if w not in STOPWORDS}


def keyword_fit(resume_text: str, jd_text: str):
    jd_words = _words(jd_text)
    if not jd_words:
        return 0, 0, 0
    common = jd_words & _words(resume_text)
    overlap = len(common) / len(jd_words)
    # about 45% overlap counts as a full match
    return min(100, round(overlap / 0.45 * 100)), len(common), len(jd_words)


def compute_scores(resume_text: str, jd_text: str) -> dict:
    jd_skills = extract_skills(jd_text)
    resume_skills = extract_skills(resume_text)
    matched = sorted(jd_skills & resume_skills)
    missing = sorted(jd_skills - resume_skills)

    # ---- Job fit (depends on the job description) ----
    kw_score, kw_common, kw_total = keyword_fit(resume_text, jd_text)
    n = len(jd_skills)

    skill_score = None
    if n:
        total_w = sum(_skill_weight(s) for s in jd_skills)
        got_w = sum(_skill_weight(s) for s in matched)
        skill_score = round(100 * got_w / total_w)

    if n >= 3:
        fit = skill_score
        fit_note = f"{len(matched)} of {n} skills from the job description found in the resume (soft skills count less)"
    elif n >= 1:
        fit = round((skill_score + kw_score) / 2)
        fit_note = (
            f"only {n} known skill(s) in the job description, so skills and keyword overlap "
            f"({kw_common} of {kw_total} keywords) are averaged (approximate)"
        )
    else:
        fit = kw_score
        fit_note = (
            f"no known technical skills in the job description, so keyword overlap is used "
            f"({kw_common} of {kw_total} keywords found in the resume) (approximate)"
        )

    # ---- Resume strength (does not depend on the job) ----
    exp, exp_note = score_experience(resume_text)
    edu, edu_note = score_education(resume_text)
    qual, qual_note = score_quality(resume_text)
    strength = round(0.4 * exp + 0.2 * edu + 0.4 * qual)

    # ---- Overall: job fit controls the result ----
    overall = round(fit * (0.7 + 0.3 * strength / 100))

    return {
        "overall": overall,
        "strength": strength,
        "breakdown": {
            "fit": {"score": fit, "note": fit_note},
            "experience": {"score": exp, "note": exp_note},
            "education": {"score": edu, "note": edu_note},
            "quality": {"score": qual, "note": qual_note},
        },
        "matched_skills": matched,
        "missing_skills": missing,
    }