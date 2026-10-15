"""Skillora AI accounts: sign up, log in, who-am-I, profile.

WHERE THE DATA IS STORED
  If the environment variable DATABASE_URL is set (it is on Render), accounts are saved in the
  Supabase PostgreSQL database. That database is permanent, so accounts survive restarts.
  If DATABASE_URL is not set (for example on your laptop), a local SQLite file skillora.db is used.

  Tables: users(id, name, email, role, salt, pw) and sessions(token, user_id, created).
  Passwords are never stored, only a salted PBKDF2-SHA256 hash.
  Login tokens are never stored either, only their SHA-256 hash.
  Uploaded resumes and reports are processed in memory and are not saved.
"""

import functools
import hashlib
import logging
import os
import secrets
import sqlite3
import ssl
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

router = APIRouter(prefix="/api/auth")
log = logging.getLogger("skillora.auth")

SQLITE_FILE = BASE / "skillora.db"
ROLES = {"student", "teacher", "company", "job seeker"}
SESSION_SECONDS = 30 * 24 * 3600   # a login lasts 30 days


# ---------------------------------------------------------------- database layer
class DbDown(Exception):
    """The database could not be reached."""


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def using_postgres() -> bool:
    return database_url().startswith(("postgres://", "postgresql://"))


def _pg_connect():
    import pg8000.dbapi   # pure Python driver, installed from requirements.txt

    u = urlparse(database_url())
    ctx = ssl.create_default_context()
    ctx.check_hostname = False          # encrypted connection; Supabase's pooler uses its own certificate
    ctx.verify_mode = ssl.CERT_NONE
    return pg8000.dbapi.connect(
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        host=u.hostname,
        port=u.port or 5432,
        database=(u.path or "").lstrip("/") or "postgres",
        ssl_context=ctx,
        timeout=15,
    )


class Cursor:
    """Returns rows as dictionaries, so row["name"] works on both databases."""

    def __init__(self, cur, pg: bool):
        self.cur, self.pg = cur, pg

    def _names(self):
        out = []
        for d in self.cur.description or []:
            name = d[0]
            out.append(name.decode() if isinstance(name, bytes) else name)
        return out

    def fetchone(self):
        if self.cur.description is None:
            return None
        row = self.cur.fetchone()
        if row is None:
            return None
        return dict(zip(self._names(), row)) if self.pg else dict(row)


class Conn:
    def __init__(self, raw, pg: bool):
        self.raw, self.pg = raw, pg

    def execute(self, sql: str, params=()):
        params = tuple(params)
        if self.pg:
            cur = self.raw.cursor()
            cur.execute(sql.replace("?", "%s"), params)
        else:
            cur = self.raw.execute(sql, params)
        return Cursor(cur, self.pg)

    def insert_id(self, sql: str, params=()) -> int:
        """Run an INSERT and return the new row's id."""
        if self.pg:
            return self.execute(sql + " RETURNING id", params).fetchone()["id"]
        return self.raw.execute(sql, tuple(params)).lastrowid

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


_schema_ready = False
_schema_lock = threading.Lock()


def _ensure_schema(con: Conn):
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        if con.pg:
            statements = [
                "CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, "
                "email TEXT NOT NULL UNIQUE, role TEXT NOT NULL, salt TEXT NOT NULL, pw TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, "
                "user_id BIGINT NOT NULL, created DOUBLE PRECISION NOT NULL)",
            ]
        else:
            statements = [
                "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, "
                "email TEXT UNIQUE, role TEXT, salt TEXT, pw TEXT)",
                "CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, "
                "user_id INTEGER, created REAL)",
            ]
        statements.append("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
        for s in statements:
            con.execute(s)
        con.commit()
        _schema_ready = True


@contextmanager
def session():
    """One short database connection per request. Commits on success, rolls back on error, always closes."""
    pg = using_postgres()
    try:
        if pg:
            raw = _pg_connect()
        else:
            raw = sqlite3.connect(SQLITE_FILE, timeout=10)
            raw.row_factory = sqlite3.Row
    except Exception as e:
        raise DbDown(str(e))
    con = Conn(raw, pg)
    try:
        _ensure_schema(con)
        yield con
        con.commit()
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            con.close()
        except Exception:
            pass


# ---------------------------------------------------------------- helpers
def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def err(msg: str, code: int = 400):
    return JSONResponse({"error": msg}, status_code=code)


def public(row) -> dict:
    return {"name": row["name"], "email": row["email"], "role": row["role"]}


def token_of(authorization: str) -> str:
    return authorization.removeprefix("Bearer ").strip()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(con: Conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    con.execute("DELETE FROM sessions WHERE created < ?", (now - SESSION_SECONDS,))   # tidy expired logins
    con.execute("INSERT INTO sessions(token, user_id, created) VALUES(?,?,?)", (_digest(token), user_id, now))
    return token


def current_user(authorization: str = "", con: Conn = None):
    """The logged-in user's row (a dictionary), or None. Other files may also call this."""
    token = token_of(authorization)
    if not token:
        return None
    if con is None:
        with session() as c:
            return current_user(authorization, c)
    return con.execute(
        "SELECT u.id, u.name, u.email, u.role, u.salt, u.pw FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token=? AND s.created>?",
        (_digest(token), time.time() - SESSION_SECONDS),
    ).fetchone()


def safe(fn):
    """Turn any database trouble into a clean JSON error instead of a crash."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DbDown:
            log.exception("database not reachable")
            return err("The database is not reachable right now. Please try again in a minute.", 503)
        except Exception:
            log.exception("account service error")
            return err("Something went wrong on the server. Please try again.", 500)

    return wrapper


# ---------------------------------------------------------------- request models
class Signup(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"


class Login(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    name: str
    role: str


class PasswordChange(BaseModel):
    current: str
    new: str


class AccountDelete(BaseModel):
    password: str


# ---------------------------------------------------------------- routes
@router.post("/signup")
@safe
def signup(body: Signup):
    name, email, role = body.name.strip(), body.email.strip().lower(), body.role.strip().lower()
    if len(name) < 2:
        return err("Enter your full name.")
    if "@" not in email or "." not in email.split("@")[-1]:
        return err("Enter a valid email address.")
    if len(body.password) < 6:
        return err("Password must be at least 6 characters.")
    if role not in ROLES:
        return err("Choose a valid role.")
    exists = "An account with this email already exists. Log in instead."
    with session() as con:
        if con.execute("SELECT 1 AS x FROM users WHERE email=?", (email,)).fetchone():
            return err(exists, 409)
        salt = secrets.token_hex(16)
        try:
            user_id = con.insert_id("INSERT INTO users(name,email,role,salt,pw) VALUES(?,?,?,?,?)",
                                    (name, email, role, salt, hash_pw(body.password, salt)))
        except Exception:
            con.rollback()   # two sign-ups with the same email at the same moment
            if con.execute("SELECT 1 AS x FROM users WHERE email=?", (email,)).fetchone():
                return err(exists, 409)
            raise
        token = new_session(con, user_id)
    return {"token": token, "user": {"name": name, "email": email, "role": role}}


@router.post("/login")
@safe
def login(body: Login):
    with session() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
        if not row or not secrets.compare_digest(row["pw"], hash_pw(body.password, row["salt"])):
            return err("Wrong email or password.", 401)
        token = new_session(con, row["id"])
    return {"token": token, "user": public(row)}


@router.get("/me")
@safe
def me(authorization: str = Header(default="")):
    row = current_user(authorization)
    return {"user": public(row)} if row else err("Please log in.", 401)


@router.post("/logout")
@safe
def logout(authorization: str = Header(default="")):
    token = token_of(authorization)
    with session() as con:
        con.execute("DELETE FROM sessions WHERE token=?", (_digest(token),))
    return {"ok": True}


@router.put("/profile")
@safe
def update_profile(body: ProfileUpdate, authorization: str = Header(default="")):
    name, role = body.name.strip(), body.role.strip().lower()
    with session() as con:
        row = current_user(authorization, con)
        if not row:
            return err("Please log in.", 401)
        if len(name) < 2:
            return err("Enter your full name.")
        if role not in ROLES:
            return err("Choose a valid role.")
        con.execute("UPDATE users SET name=?, role=? WHERE id=?", (name, role, row["id"]))
    return {"user": {"name": name, "email": row["email"], "role": role}}


@router.post("/password")
@safe
def change_password(body: PasswordChange, authorization: str = Header(default="")):
    with session() as con:
        row = current_user(authorization, con)
        if not row:
            return err("Please log in.", 401)
        if not secrets.compare_digest(row["pw"], hash_pw(body.current, row["salt"])):
            return err("Your current password is wrong.", 400)
        if len(body.new) < 6:
            return err("New password must be at least 6 characters.")
        salt = secrets.token_hex(16)
        con.execute("UPDATE users SET salt=?, pw=? WHERE id=?", (salt, hash_pw(body.new, salt), row["id"]))
        # log out every other device, keep this one
        con.execute("DELETE FROM sessions WHERE user_id=? AND token<>?",
                    (row["id"], _digest(token_of(authorization))))
    return {"ok": True}


@router.post("/delete")
@safe
def delete_account(body: AccountDelete, authorization: str = Header(default="")):
    with session() as con:
        row = current_user(authorization, con)
        if not row:
            return err("Please log in.", 401)
        if not secrets.compare_digest(row["pw"], hash_pw(body.password, row["salt"])):
            return err("Password is wrong.", 400)
        con.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        con.execute("DELETE FROM users WHERE id=?", (row["id"],))
    return {"ok": True}


@router.post("/logout-all")
@safe
def logout_all(authorization: str = Header(default="")):
    with session() as con:
        row = current_user(authorization, con)
        if not row:
            return err("Please log in.", 401)
        con.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
    return {"ok": True}


@router.get("/dbinfo")
@safe
def dbinfo():
    """Shows which database the site is using. Open /api/auth/dbinfo to check."""
    with session() as con:
        count = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    return {"database": "supabase-postgres" if using_postgres() else "local-sqlite-file", "users": count}