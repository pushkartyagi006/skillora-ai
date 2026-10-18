"""History: every user's saved results and drafts, so they can open them again any time.

What is stored (table: history): kind, title, a short summary, an optional score, and the result itself as JSON.
What is NOT stored: uploaded files (resumes, reports). Only the results the page already shows.
Each person can only ever see, change or delete their own items.
"""

import json
import math
import time
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from auth import current_user, err, safe, session

router = APIRouter(prefix="/api/history")

KINDS = {"resume_check", "resume_build", "teacher", "hiring", "interview", "project"}
MAX_PAYLOAD_BYTES = 600_000     # one saved item
MAX_ITEMS = 80                  # per user; the oldest items are removed beyond this


class ItemIn(BaseModel):
    kind: str
    title: str = ""
    summary: str = ""
    score: Optional[float] = None
    payload: dict = {}


class ItemPatch(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    score: Optional[float] = None
    payload: Optional[dict] = None


class ClearIn(BaseModel):
    kind: Optional[str] = None


def _clip(text, n):
    return " ".join(str(text or "").split())[:n]


def _score(v):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _dump(payload):
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return text if len(text.encode("utf-8")) <= MAX_PAYLOAD_BYTES else None


def _public(row, with_payload=False):
    out = {"id": row["id"], "kind": row["kind"], "title": row["title"], "summary": row["summary"],
           "score": row["score"], "created_at": row["created_at"], "updated_at": row["updated_at"]}
    if with_payload:
        out["payload"] = json.loads(row["payload"])
    return out


@router.post("")
@safe
def save_item(body: ItemIn, authorization: str = Header(default="")):
    if body.kind not in KINDS:
        return err("Unknown kind of history item.")
    text = _dump(body.payload)
    if text is None:
        return err("This result is too large to save (the limit is about 600 KB).", 413)
    title = _clip(body.title, 120) or "Untitled"
    now = time.time()
    with session() as con:
        user = current_user(authorization, con)
        if not user:
            return err("Please log in.", 401)
        new_id = con.insert_id(
            "INSERT INTO history(user_id, kind, title, summary, score, payload, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (user["id"], body.kind, title, _clip(body.summary, 300), _score(body.score), text, now, now))
        # keep only the newest MAX_ITEMS items for this user
        ids = [r["id"] for r in _all(con, user["id"])]
        for old_id in ids[MAX_ITEMS:]:
            con.execute("DELETE FROM history WHERE id=? AND user_id=?", (old_id, user["id"]))
    return {"id": new_id}


def _all(con, user_id):
    cur = con.execute("SELECT id FROM history WHERE user_id=? ORDER BY updated_at DESC, id DESC", (user_id,))
    rows = []
    while True:
        r = cur.fetchone()
        if r is None:
            return rows
        rows.append(r)


@router.get("")
@safe
def list_items(kind: str = "", limit: int = 100, authorization: str = Header(default="")):
    limit = max(1, min(int(limit), MAX_ITEMS))
    with session() as con:
        user = current_user(authorization, con)
        if not user:
            return err("Please log in.", 401)
        sql = "SELECT id, kind, title, summary, score, created_at, updated_at FROM history WHERE user_id=?"
        args = [user["id"]]
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        sql += " ORDER BY updated_at DESC, id DESC"
        cur = con.execute(sql, args)
        items = []
        while len(items) < limit:
            r = cur.fetchone()
            if r is None:
                break
            items.append(_public(r))
    return {"items": items}


@router.get("/{item_id}")
@safe
def get_item(item_id: int, authorization: str = Header(default="")):
    with session() as con:
        user = current_user(authorization, con)
        if not user:
            return err("Please log in.", 401)
        row = con.execute("SELECT * FROM history WHERE id=? AND user_id=?", (item_id, user["id"])).fetchone()
    if not row:
        return err("That saved item was not found.", 404)
    return {"item": _public(row, with_payload=True)}


@router.put("/{item_id}")
@safe
def update_item(item_id: int, body: ItemPatch, authorization: str = Header(default="")):
    sets, args = [], []
    if body.title is not None:
        sets.append("title=?"); args.append(_clip(body.title, 120) or "Untitled")
    if body.summary is not None:
        sets.append("summary=?"); args.append(_clip(body.summary, 300))
    if body.score is not None:
        sets.append("score=?"); args.append(_score(body.score))
    if body.payload is not None:
        text = _dump(body.payload)
        if text is None:
            return err("This result is too large to save (the limit is about 600 KB).", 413)
        sets.append("payload=?"); args.append(text)
    sets.append("updated_at=?"); args.append(time.time())
    with session() as con:
        user = current_user(authorization, con)
        if not user:
            return err("Please log in.", 401)
        if not con.execute("SELECT 1 AS x FROM history WHERE id=? AND user_id=?", (item_id, user["id"])).fetchone():
            return err("That saved item was not found.", 404)
        con.execute("UPDATE history SET " + ", ".join(sets) + " WHERE id=? AND user_id=?", args + [item_id, user["id"]])
    return {"ok": True}


@router.delete("/{item_id}")
@safe
def delete_item(item_id: int, authorization: str = Header(default="")):
    with session() as con:
        user = current_user(authorization, con)
        if not user:
            return err("Please log in.", 401)
        if not con.execute("SELECT 1 AS x FROM history WHERE id=? AND user_id=?", (item_id, user["id"])).fetchone():
            return err("That saved item was not found.", 404)
        con.execute("DELETE FROM history WHERE id=? AND user_id=?", (item_id, user["id"]))
    return {"ok": True}


@router.post("/clear")
@safe
def clear_items(body: ClearIn, authorization: str = Header(default="")):
    with session() as con:
        user = current_user(authorization, con)
        if not user:
            return err("Please log in.", 401)
        if body.kind:
            con.execute("DELETE FROM history WHERE user_id=? AND kind=?", (user["id"], body.kind))
        else:
            con.execute("DELETE FROM history WHERE user_id=?", (user["id"],))
    return {"ok": True}
