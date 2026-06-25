
import os
import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    openai as lk_openai,
    cartesia,
    deepgram,
    silero,
)
from livekit.agents import function_tool

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

SYSTEM_PROMPT = """You are Mykare's AI front-desk assistant — warm, professional, and efficient. 
You help patients with healthcare appointment booking and management.

Your personality:
- Friendly but concise (keep responses under 2 sentences when possible)
- Always confirm important details back to the user
- Handle one thing at a time

Workflow:
1. Greet the user and ask for their phone number (identify_user)
2. Understand their intent (book / view / cancel / reschedule appointment)
3. Call the appropriate tool
4. Confirm the outcome clearly
5. Ask if there's anything else
6. When done, call end_conversation which will generate a summary

ALWAYS extract: Name, Phone, Date, Time, Intent from the conversation.
ALWAYS call a tool before responding about appointments.
"""


async def api_post(path: str, payload: dict) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE_URL}{path}", json=payload) as r:
            return await r.json()

async def api_get(path: str, params: dict = {}) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{BASE_URL}{path}", params=params) as r:
            return await r.json()


# ── Agent ─────────────────────────────────────────────────────────────────────

class MykareAgent(Agent):
    def __init__(self):
        super().__init__(instructions=SYSTEM_PROMPT)
        self.user_phone: Optional[str] = None
        self.user_name: Optional[str] = None
        self.conversation_log: list = []

    @function_tool()
    async def identify_user(self, phone: str, name: Optional[str] = None) -> str:
        """Identify or register the user by phone number. Call this first."""
        result = await api_post("/api/tools/identify_user", {"phone": phone, "name": name})
        self.user_phone = phone
        if name:
            self.user_name = name
        return json.dumps(result)

    @function_tool()
    async def fetch_slots(self, date: Optional[str] = None) -> str:
        """Fetch available appointment slots. Optionally pass a date (YYYY-MM-DD)."""
        params = {"date": date} if date else {}
        result = await api_get("/api/tools/fetch_slots", params)
        # Return only first 5 slots to keep response brief
        if "slots" in result:
            result["slots"] = result["slots"][:5]
        return json.dumps(result)

    @function_tool()
    async def book_appointment(self, date: str, time: str, user_name: str) -> str:
        """Book an appointment. Args: date (YYYY-MM-DD), time (HH:MM), user_name."""
        if not self.user_phone:
            return json.dumps({"error": "Please identify the user first."})
        result = await api_post("/api/tools/book_appointment", {
            "user_phone": self.user_phone,
            "user_name": user_name or self.user_name or "Patient",
            "date": date,
            "time": time,
        })
        if self.user_name is None and user_name:
            self.user_name = user_name
        return json.dumps(result)

    @function_tool()
    async def retrieve_appointments(self) -> str:
        """Get all appointments for the current user."""
        if not self.user_phone:
            return json.dumps({"error": "Please identify the user first."})
        result = await api_get("/api/tools/retrieve_appointments", {"phone": self.user_phone})
        return json.dumps(result)

    @function_tool()
    async def cancel_appointment(self, appointment_id: int) -> str:
        """Cancel an appointment by its ID."""
        result = await api_post("/api/tools/cancel_appointment",
                                {"appointment_id": appointment_id})
        return json.dumps(result)

    @function_tool()
    async def modify_appointment(self, appointment_id: int,
                                  new_date: str, new_time: str) -> str:
        """Reschedule an existing appointment."""
        result = await api_post("/api/tools/modify_appointment", {
            "appointment_id": appointment_id,
            "new_date": new_date,
            "new_time": new_time,
        })
        return json.dumps(result)

    @function_tool()
    async def end_conversation(self, summary: str, preferences: Optional[str] = None) -> str:
        """
        End the conversation and generate summary.
        Args: summary (text summary of the call), preferences (optional JSON string of noted preferences)
        """
        appts_result = await api_get("/api/tools/retrieve_appointments",
                                      {"phone": self.user_phone or ""})
        appts = appts_result.get("appointments", [])
        prefs = {}
        if preferences:
            try:
                prefs = json.loads(preferences)
            except Exception:
                prefs = {"notes": preferences}

        await api_post("/api/tools/save_summary", {
            "user_phone": self.user_phone or "unknown",
            "summary": summary,
            "appointments": appts,
            "preferences": prefs,
        })
        return json.dumps({
            "status": "ended",
            "summary": summary,
            "appointments": appts,
            "preferences": prefs,
            "timestamp": datetime.now().isoformat(),
        })


# ── Entry Point ───────────────────────────────────────────────────────────────

def create_session() -> AgentSession:
    return AgentSession(
        stt=deepgram.STT(model="nova-2", language="en"),
        llm=lk_openai.LLM(model="gpt-4o"),
        tts=cartesia.TTS(voice="79a125e8-cd45-4c13-8a67-188112f4dd22"),  # Friendly voice
        vad=silero.VAD.load(),
        turn_detection=agents.MultimodalAgent.DEFAULT_TURN_DETECTION,
    )


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()
    session = create_session()
    agent = MykareAgent()

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    await session.generate_reply(
        instructions="Greet the user warmly as Mykare's AI assistant and ask how you can help them today."
    )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
