

import os
import json
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# ── Database Setup ────────────────────────────────────────────────────────────

DB_PATH = "mykare.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT NOT NULL,
            user_name TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT DEFAULT 'confirmed',
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, time, status)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS call_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT,
            summary TEXT,
            appointments_json TEXT,
            preferences_json TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Mykare Voice AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Models ───────────────────────────────────────────────────────────

class UserIdentify(BaseModel):
    phone: str
    name: Optional[str] = None

class AppointmentBook(BaseModel):
    user_phone: str
    user_name: str
    date: str   # YYYY-MM-DD
    time: str   # HH:MM

class AppointmentModify(BaseModel):
    appointment_id: int
    new_date: str
    new_time: str

class AppointmentCancel(BaseModel):
    appointment_id: int

class CallSummary(BaseModel):
    user_phone: str
    summary: str
    appointments: list
    preferences: dict


# ── Tool Functions ────────────────────────────────────────────────────────────

@app.post("/api/tools/identify_user")
async def identify_user(data: UserIdentify):
    """Register or fetch user by phone number."""
    db = get_db()
    try:
        # Upsert user
        if data.name:
            db.execute(
                "INSERT INTO users (phone, name) VALUES (?, ?) "
                "ON CONFLICT(phone) DO UPDATE SET name=excluded.name",
                (data.phone, data.name)
            )
        else:
            db.execute(
                "INSERT OR IGNORE INTO users (phone) VALUES (?)",
                (data.phone,)
            )
        db.commit()
        user = db.execute(
            "SELECT * FROM users WHERE phone = ?", (data.phone,)
        ).fetchone()
        return {"status": "ok", "user": dict(user)}
    finally:
        db.close()


@app.get("/api/tools/fetch_slots")
async def fetch_slots(date: Optional[str] = None):
    """Return available appointment slots (next 7 days, 9am-5pm hourly)."""
    db = get_db()
    try:
        base = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
        slots = []
        for day_offset in range(7):
            day = base + timedelta(days=day_offset)
            if day.weekday() >= 5:  # skip weekends
                continue
            for hour in range(9, 17):
                slot_time = f"{hour:02d}:00"
                slot_date = day.strftime("%Y-%m-%d")
                booked = db.execute(
                    "SELECT 1 FROM appointments WHERE date=? AND time=? AND status='confirmed'",
                    (slot_date, slot_time)
                ).fetchone()
                if not booked:
                    slots.append({"date": slot_date, "time": slot_time,
                                  "display": f"{day.strftime('%A, %B %d')} at {hour}:00"})
        return {"status": "ok", "slots": slots[:20]}
    finally:
        db.close()


@app.post("/api/tools/book_appointment")
async def book_appointment(data: AppointmentBook):
    """Book an appointment, prevent double booking."""
    db = get_db()
    try:
        existing = db.execute(
            "SELECT * FROM appointments WHERE date=? AND time=? AND status='confirmed'",
            (data.date, data.time)
        ).fetchone()
        if existing:
            raise HTTPException(409, "Slot already booked. Please choose another time.")

        cur = db.execute(
            "INSERT INTO appointments (user_phone, user_name, date, time) VALUES (?, ?, ?, ?)",
            (data.user_phone, data.user_name, data.date, data.time)
        )
        db.commit()
        appt_id = cur.lastrowid
        appt = db.execute(
            "SELECT * FROM appointments WHERE id=?", (appt_id,)
        ).fetchone()
        return {
            "status": "ok",
            "appointment": dict(appt),
            "confirm_message": f"Appointment confirmed for {data.user_name} on {data.date} at {data.time}."
        }
    finally:
        db.close()


@app.get("/api/tools/retrieve_appointments")
async def retrieve_appointments(phone: str):
    """Get all appointments for a user."""
    db = get_db()
    try:
        appts = db.execute(
            "SELECT * FROM appointments WHERE user_phone=? ORDER BY date, time",
            (phone,)
        ).fetchall()
        return {"status": "ok", "appointments": [dict(a) for a in appts]}
    finally:
        db.close()


@app.post("/api/tools/cancel_appointment")
async def cancel_appointment(data: AppointmentCancel):
    """Cancel an appointment by ID."""
    db = get_db()
    try:
        appt = db.execute(
            "SELECT * FROM appointments WHERE id=?", (data.appointment_id,)
        ).fetchone()
        if not appt:
            raise HTTPException(404, "Appointment not found.")
        db.execute(
            "UPDATE appointments SET status='cancelled' WHERE id=?",
            (data.appointment_id,)
        )
        db.commit()
        return {"status": "ok", "message": f"Appointment #{data.appointment_id} cancelled."}
    finally:
        db.close()


@app.post("/api/tools/modify_appointment")
async def modify_appointment(data: AppointmentModify):
    """Reschedule an appointment."""
    db = get_db()
    try:
        conflict = db.execute(
            "SELECT 1 FROM appointments WHERE date=? AND time=? AND status='confirmed'",
            (data.new_date, data.new_time)
        ).fetchone()
        if conflict:
            raise HTTPException(409, "New slot is already taken.")
        db.execute(
            "UPDATE appointments SET date=?, time=? WHERE id=?",
            (data.new_date, data.new_time, data.appointment_id)
        )
        db.commit()
        appt = db.execute(
            "SELECT * FROM appointments WHERE id=?", (data.appointment_id,)
        ).fetchone()
        return {"status": "ok", "appointment": dict(appt)}
    finally:
        db.close()


@app.post("/api/tools/save_summary")
async def save_summary(data: CallSummary):
    """Save call summary to DB."""
    db = get_db()
    try:
        db.execute(
            "INSERT INTO call_summaries (user_phone, summary, appointments_json, preferences_json) VALUES (?,?,?,?)",
            (data.user_phone, data.summary,
             json.dumps(data.appointments), json.dumps(data.preferences))
        )
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


# ── LiveKit Token Endpoint ────────────────────────────────────────────────────

@app.get("/api/livekit/token")
async def get_livekit_token(room: str = "mykare-room", identity: str = "user"):
    """Generate LiveKit access token for the frontend."""
    try:
        from livekit.api import AccessToken, VideoGrants
        token = (
            AccessToken(
                api_key=os.environ.get("LIVEKIT_API_KEY", "devkey"),
                api_secret=os.environ.get("LIVEKIT_API_SECRET", "devsecret"),
            )
            .with_identity(identity)
            .with_grants(VideoGrants(room_join=True, room=room))
            .to_jwt()
        )
        return {
            "token": token,
            "url": os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
        }
    except ImportError:
        # Return a mock token if livekit not installed
        return {
            "token": "mock-token-install-livekit-agents",
            "url": os.environ.get("LIVEKIT_URL", "ws://localhost:7880"),
            "warning": "livekit package not installed"
        }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Mykare Voice AI"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
