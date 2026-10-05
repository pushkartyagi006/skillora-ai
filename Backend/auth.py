"""Skillora AI accounts: sign up, log in, who-am-I, profile. Uses SQLite (built into Python)."""

import hashlib
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth")
DB_FILE = Path(__file__).resolve().parent / "skillora.db"
ROLES = {"student", "teacher", "company", "job seeker"}


def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, "
                "email TEXT UNIQUE, role TEXT, salt TEXT, pw TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, "
                "user_id INTEGER, created REAL)")
    return con


def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def err(msg: str, code: int = 400):
    return JSONResponse({"error": msg}, status_code=code)


def public(row) -> dict:
    return {"name": row["name"], "email": row["email"], "role": row["role"]}


def new_session(con, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    con.execute("INSERT INTO sessions VALUES(?,?,?)", (token, user_id, time.time()))
    con.commit()
    return token


class Signup(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"


class Login(BaseModel):
    email: str
    password: str


@router.post("/signup")
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
    con = db()
    if con.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        return err("An account with this email already exists. Log in instead.", 409)
    salt = secrets.token_hex(16)
    cur = con.execute("INSERT INTO users(name,email,role,salt,pw) VALUES(?,?,?,?,?)",
                      (name, email, role, salt, hash_pw(body.password, salt)))
    con.commit()
    token = new_session(con, cur.lastrowid)
    row = con.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"token": token, "user": public(row)}


@router.post("/login")
def login(body: Login):
    con = db()
    row = con.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
    if not row or not secrets.compare_digest(row["pw"], hash_pw(body.password, row["salt"])):
        return err("Wrong email or password.", 401)
    return {"token": new_session(con, row["id"]), "user": public(row)}


def current_user(authorization: str = ""):
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None
    con = db()
    return con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                       "WHERE s.token=?", (token,)).fetchone()


@router.get("/me")
def me(authorization: str = Header(default="")):
    row = current_user(authorization)
    return {"user": public(row)} if row else err("Please log in.", 401)


@router.post("/logout")
def logout(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    con = db()
    con.execute("DELETE FROM sessions WHERE token=?", (token,))
    con.commit()
    return {"ok": True}


# ---------- Profile page ----------

class ProfileUpdate(BaseModel):
    name: str
    role: str


class PasswordChange(BaseModel):
    current: str
    new: str


class AccountDelete(BaseModel):
    password: str


def token_of(authorization: str) -> str:
    return authorization.removeprefix("Bearer ").strip()


@router.put("/profile")
def update_profile(body: ProfileUpdate, authorization: str = Header(default="")):
    row = current_user(authorization)
    if not row:
        return err("Please log in.", 401)
    name, role = body.name.strip(), body.role.strip().lower()
    if len(name) < 2:
        return err("Enter your full name.")
    if role not in ROLES:
        return err("Choose a valid role.")
    con = db()
    con.execute("UPDATE users SET name=?, role=? WHERE id=?", (name, role, row["id"]))
    con.commit()
    return {"user": public(con.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone())}


@router.post("/password")
def change_password(body: PasswordChange, authorization: str = Header(default="")):
    row = current_user(authorization)
    if not row:
        return err("Please log in.", 401)
    if not secrets.compare_digest(row["pw"], hash_pw(body.current, row["salt"])):
        return err("Your current password is wrong.", 400)
    if len(body.new) < 6:
        return err("New password must be at least 6 characters.")
    salt = secrets.token_hex(16)
    con = db()
    con.execute("UPDATE users SET salt=?, pw=? WHERE id=?", (salt, hash_pw(body.new, salt), row["id"]))
    # log out every other device, keep this one
    con.execute("DELETE FROM sessions WHERE user_id=? AND token<>?", (row["id"], token_of(authorization)))
    con.commit()
    return {"ok": True}


@router.post("/delete")
def delete_account(body: AccountDelete, authorization: str = Header(default="")):
    row = current_user(authorization)
    if not row:
        return err("Please log in.", 401)
    if not secrets.compare_digest(row["pw"], hash_pw(body.password, row["salt"])):
        return err("Password is wrong.", 400)
    con = db()
    con.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
    con.execute("DELETE FROM users WHERE id=?", (row["id"],))
    con.commit()
    return {"ok": True}


@router.post("/logout-all")
def logout_all(authorization: str = Header(default="")):
    row = current_user(authorization)
    if not row:
        return err("Please log in.", 401)
    con = db()
    con.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
    con.commit()
    return {"ok": True}
