"""My Journey: adds up a user's saved History into progress numbers, score trends and simple insights.

It only READS the history table (see history.py). Nothing here calls the AI, so it is free and instant.
Each person only ever sees their own numbers.
"""

import json

from fastapi import APIRouter, Header

from auth import current_user, err, safe, session

router = APIRouter(prefix="/api/journey")

KINDS = ("resume_check", "resume_build", "teacher", "hiring", "interview", "project")
TREND_KINDS = ("resume_check", "project", "interview")
TREND_POINTS = 12        # how many of the latest scores each trend shows


def _payloads(con, user_id, kind, limit):
    """The newest `limit` saved results of one kind, with their data (so we can read skills and roadmaps)."""
    cur = con.execute("SELECT id, payload FROM history WHERE user_id=? AND kind=? ORDER BY updated_at DESC, id DESC LIMIT ?",
                      (user_id, kind, limit))
    rows = []
    while True:
        r = cur.fetchone()
        if r is None:
            return rows
        try:
            data = json.loads(r["payload"])
        except ValueError:
            continue
        if isinstance(data, dict):
            rows.append((r["id"], data))


def _missing_skills(checks):
    """Skills that were missing in two or more of the latest resume checks."""
    counts = {}
    for _id, payload in checks:
        scores = ((payload.get("data") or {}).get("scores") or {}) if isinstance(payload.get("data"), dict) else {}
        skills = scores.get("missing_skills")
        if not isinstance(skills, list):
            continue
        for s in {str(x).strip().lower() for x in skills if str(x).strip()}:
            counts[s] = counts.get(s, 0) + 1
    ranked = sorted(((n, s) for s, n in counts.items() if n >= 2), key=lambda x: (-x[0], x[1]))
    return [{"skill": s, "count": n} for n, s in ranked[:5]]


def _project_fix(projects):
    """The biggest improvement step from the newest analysed project that has a roadmap."""
    for item_id, payload in projects:
        state = payload.get("state")
        if not isinstance(state, dict):
            continue
        roadmap = state.get("roadmap")
        if not isinstance(roadmap, list) or not roadmap or not isinstance(roadmap[0], dict):
            continue
        step = roadmap[0]
        try:
            gain = int(step.get("gain") or 0)
        except (TypeError, ValueError):
            gain = 0
        return {"item_id": item_id, "project": str(state.get("title") or "your project")[:120],
                "score": state.get("overall"), "step": str(step.get("title") or "")[:160],
                "gain": gain, "why": str(step.get("why") or "")[:240]}
    return None


@router.get("")
@safe
def journey(authorization: str = Header(default="")):
    with session() as con:
        user = current_user(authorization, con)
        if not user:
            return err("Please log in.", 401)
        uid = user["id"]
        cur = con.execute("SELECT id, kind, title, score, created_at, updated_at FROM history WHERE user_id=? "
                          "ORDER BY created_at ASC, id ASC", (uid,))
        rows = []
        while True:
            r = cur.fetchone()
            if r is None:
                break
            rows.append(r)
        checks = _payloads(con, uid, "resume_check", 5)
        projects = _payloads(con, uid, "project", 3)

    counts = {k: 0 for k in KINDS}
    for r in rows:
        if r["kind"] in counts:
            counts[r["kind"]] += 1

    trends = {}
    for kind in TREND_KINDS:
        pts = [{"id": r["id"], "t": r["created_at"], "score": r["score"], "title": r["title"]}
               for r in rows if r["kind"] == kind and r["score"] is not None]
        trends[kind] = pts[-TREND_POINTS:]

    activity = sorted({int(r[col]) for r in rows for col in ("created_at", "updated_at")})
    newest = max(rows, key=lambda r: (r["updated_at"], r["id"])) if rows else None
    latest = ({"id": newest["id"], "kind": newest["kind"], "title": newest["title"], "updated_at": newest["updated_at"]}
              if newest else None)

    return {
        "total": len(rows),
        "counts": counts,
        "trends": trends,
        "activity": activity,
        "latest": latest,
        "insights": {
            "missing_skills": _missing_skills(checks),
            "checks_considered": len(checks),
            "project_fix": _project_fix(projects),
        },
    }
