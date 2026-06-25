# 🎙️ Mykare Voice AI Agent

A real-world AI voice agent for healthcare appointment management.

**Stack:** LiveKit Agents · Deepgram STT · Cartesia TTS · OpenAI GPT-4o · FastAPI · SQLite · React + Vite

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (React + Vite)                                      │
│  ┌──────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │ TalkingAvatar│  │  ToolEventFeed  │  │  CallSummary  │  │
│  └──────┬───────┘  └────────┬────────┘  └───────┬───────┘  │
│         │   LiveKit SDK     │                    │          │
└─────────┼───────────────────┼────────────────────┼──────────┘
          │ WebRTC            │ DataChannel        │
          ▼                   ▼                    │
┌─────────────────────────┐                       │
│  LiveKit Server (cloud) │                       │
└───────────┬─────────────┘                       │
            │ Agent SDK                            │ REST
            ▼                                     ▼
┌─────────────────────────┐  ┌───────────────────────────────┐
│  Agent Worker (Python)  │  │  FastAPI Backend              │
│  ┌────────┐ ┌────────┐  │  │  /api/tools/*                 │
│  │Deepgram│ │Cartesia│  │──▶  /api/livekit/token           │
│  │  STT   │ │  TTS   │  │  │  /health                      │
│  └────────┘ └────────┘  │  └──────────────┬────────────────┘
│  ┌────────┐ ┌────────┐  │                 │
│  │GPT-4o  │ │Silero  │  │                 ▼
│  │  LLM   │ │  VAD   │  │         ┌──────────────┐
│  └────────┘ └────────┘  │         │  SQLite DB   │
└─────────────────────────┘         │  users       │
                                    │  appointments│
                                    │  summaries   │
                                    └──────────────┘
```

---

## Prerequisites

- Node.js 18+
- Python 3.11+
- A [LiveKit Cloud](https://livekit.io) account (free tier works)
- API keys: Deepgram, Cartesia, OpenAI

---

## Backend Setup

```bash
cd backend

# Create virtualenv
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# → Fill in your API keys in .env

# Start the FastAPI server
python main.py

# In a SEPARATE terminal, start the LiveKit agent worker
python agent.py dev
```

The FastAPI server runs on `http://localhost:8000`.

### Tool Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/tools/identify_user` | Register/fetch user by phone |
| GET | `/api/tools/fetch_slots` | Get available appointment slots |
| POST | `/api/tools/book_appointment` | Book (with double-booking prevention) |
| GET | `/api/tools/retrieve_appointments` | List user's appointments |
| POST | `/api/tools/cancel_appointment` | Cancel by ID |
| POST | `/api/tools/modify_appointment` | Reschedule |
| POST | `/api/tools/save_summary` | Persist call summary |
| GET | `/api/livekit/token` | Issue LiveKit JWT |

---

## Frontend Setup

```bash
cd frontend

npm install

# Configure
cp .env.example .env
# VITE_BACKEND_URL=http://localhost:8000

npm run dev
# → http://localhost:3000
```

---

## How It Works

1. User clicks **Start Call** → frontend fetches a LiveKit JWT from the backend
2. Browser joins the LiveKit room via WebRTC; microphone goes live
3. Agent worker (Python) joins the same room
4. **Deepgram** transcribes speech in real time (<300ms)
5. **GPT-4o** decides whether to call a tool or respond
6. Tool calls hit the FastAPI backend (`/api/tools/*`) which reads/writes SQLite
7. Tool events are broadcast over the LiveKit data channel → shown in the UI
8. **Cartesia** synthesises the response as audio (streamed)
9. Avatar animates in sync with agent audio level
10. On `end_conversation`, a summary is generated and displayed within 10 seconds

---

## Deployment

### Backend (Railway / Render / Fly.io)

```bash
# Dockerfile-free: Railway auto-detects Python
# Set env vars in dashboard, then:
railway up
```

### Agent Worker

```bash
# Must run as a long-lived process (not serverless)
# Railway: set start command to: python agent.py start
# Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET etc.
```

### Frontend (Vercel / Netlify)

```bash
cd frontend
npm run build
# Deploy the dist/ folder
# Set VITE_BACKEND_URL to your production backend URL
```

---

## Cost Breakdown (per call)

| Component | Provider | ~Cost |
|-----------|----------|-------|
| STT | Deepgram Nova-2 | $0.0043 / min |
| LLM | GPT-4o | ~$0.005–0.02 / call |
| TTS | Cartesia | $0.000015 / char |
| LiveKit | Cloud | $0.002 / participant-min |
| **Total 5-min call** | | **~$0.05–0.10** |

---

