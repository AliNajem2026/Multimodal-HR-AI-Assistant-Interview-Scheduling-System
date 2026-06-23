# Multimodal HR AI Assistant — Interview Scheduling System

An end-to-end agentic application that automates technical interview scheduling using **Claude AI** (Anthropic) for natural-language parsing, **real-time calendar slot generation**, **Google Calendar** for event creation, and **Gmail** for automated candidate notifications.

---

## What It Does

A recruiter pastes a raw candidate email or form submission into the UI. The system then:

1. **Parses** the unstructured text with Claude AI to extract the candidate's name, email, role, and department.
2. **Proposes** three interview slots spread across Mon / Wed / Fri of the target week at varied times (10 AM, 2 PM, 4 PM) — using Google Calendar free/busy when credentials are available, or a real-date local generator otherwise.
3. **Advances** to the following week's slots if the candidate declines the current proposals.
4. **Creates** a Google Calendar event with a Google Meet link when the recruiter confirms a slot.
5. **Emails** the candidate a confirmation with the meeting time and Meet link.
6. **Saves** all candidate records to a SQLite database.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Streamlit Frontend  (frontend/app.py · port 8501)              │
│  Phase 1: Paste text → Phase 2: Pick slot → Phase 3: Confirmed  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP
┌───────────────────────────▼─────────────────────────────────────┐
│  FastAPI Backend  (app/main.py · port 8000)                     │
│                                                                 │
│  POST /api/v1/schedule/request                                  │
│    └── InterviewParsingAgent  (Claude Haiku via LangChain)      │
│    └── _get_slots() → GoogleCalendarService or local generator  │
│    └── SQLite: upsert CandidateRecord                           │
│                                                                 │
│  POST /api/v1/schedule/more-slots                               │
│    └── _get_slots(week_offset=N) → next-week slots              │
│                                                                 │
│  POST /api/v1/schedule/confirm                                  │
│    └── GoogleCalendarService.create_interview_event()           │
│    └── EmailService.send_confirmation()  (Gmail SMTP)           │
│    └── SQLite: update status + event_id                         │
└─────────────────────────────────────────────────────────────────┘
```

### Key components

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI entrypoint, CORS, DB table creation |
| `app/config.py` | All settings loaded from `.env` |
| `app/agents/parser_agent.py` | Claude Haiku structured-output extraction via LangChain |
| `app/services/google_calendar.py` | Google Calendar OAuth + free/busy + event creation |
| `app/services/email_service.py` | Gmail SMTP confirmation email (Python stdlib) |
| `app/routers/scheduler.py` | `/request`, `/more-slots`, `/confirm` endpoints |
| `app/database/connection.py` | SQLAlchemy engine + session |
| `app/database/models.py` | `CandidateRecord` ORM model |
| `frontend/app.py` | Streamlit 3-phase UI |

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)
- (Optional) Google Cloud project with Calendar API enabled
- (Optional) Gmail account with an App Password for email notifications

### 2. Clone & install

```bash
git clone <repo-url>
cd "Interview Scheduling system"
pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env` and fill in your values:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-api03-...

# Optional — Google Calendar integration
GOOGLE_APPLICATION_CREDENTIALS=credentials.json

# Optional — Email notifications
EMAIL_ENABLED=true
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD=your_16_char_app_password
```

Without `credentials.json` the app generates real-date slots locally (Mon/Wed/Fri at 10 AM / 2 PM / 4 PM).  
Without email settings the app still works; emails are simply skipped.

### 4. Run

```bash
# Terminal 1 — backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
streamlit run frontend/app.py
```

- Backend API: `http://127.0.0.1:8000`
- Interactive docs: `http://127.0.0.1:8000/docs`
- Frontend: `http://localhost:8501`

---

## Docker

```bash
docker compose up --build
```

This starts both services automatically. The frontend is wired to the backend via the internal Docker network.

| Service | Port |
|---------|------|
| Backend (FastAPI) | 8000 |
| Frontend (Streamlit) | 8501 |

The SQLite database is persisted in the `db_data` named volume. To enable Google Calendar inside Docker, uncomment the credential volume lines in `docker-compose.yml`.

### Run tests inside Docker

```bash
docker compose run --rm test
```

---

## Testing

The project has a full test suite covering all endpoints and core services. Tests run against an in-memory SQLite database and mock all external calls (Claude AI, Google Calendar, SMTP) so no credentials are needed.

```bash
# Run all tests
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=app --cov-report=term-missing
```

### Test structure

```
tests/
├── conftest.py                       # In-memory DB, TestClient, shared fixtures
├── unit/
│   ├── test_slot_generation.py       # _generate_week_slots(), _week_label()
│   ├── test_parser_agent.py          # Claude extraction logic (mocked LLM)
│   └── test_email_service.py         # SMTP send + error handling (mocked SMTP)
└── integration/
    └── test_scheduler_api.py         # All 3 endpoints — 200/201/422/404/503 paths
```

**49 tests, ~0.5 s.** All external I/O is mocked — no API keys, no network, no SMTP needed to run.

---

## Usage Walkthrough

### Phase 1 — Paste candidate text

Paste any unstructured email or form submission:

```
Hi, I'm Sarah Johnson (sarah.johnson@example.com).
I'd like to apply for the Senior Backend Engineer position.
I have 7 years of Python and Go experience.
```

Click **Process with Claude AI**. Claude extracts name, email, role, and department.

### Phase 2 — Select a slot

Three interview slots are displayed for the upcoming week:

- Monday — 10:00 AM
- Wednesday — 2:00 PM
- Friday — 4:00 PM

Click any slot to confirm, or click **"None of these work — suggest the following week"** to advance to the next week's slots.

### Phase 3 — Confirmation

A Google Calendar event is created with all panel members and a Google Meet link. If `EMAIL_ENABLED=true`, a confirmation email is automatically sent to the candidate with the time and Meet URL.

---

## Google Calendar Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable the **Google Calendar API**.
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**.
4. Select **Desktop app**, download the JSON, save as `credentials.json` in the project root.
5. Set `GOOGLE_APPLICATION_CREDENTIALS=credentials.json` in `.env`.
6. On first run the browser opens for OAuth consent. A `token.json` is saved for subsequent runs.

### Panel directory

The interview panel is defined in `app/routers/scheduler.py`:

```python
PANEL_DIRECTORY = {
    "Engineering": ["alice@company.com", "bob@company.com", "charlie@company.com"],
    "Product": ["diana@company.com", "evan@company.com"],
}
```

Replace these with real email addresses. When Google Calendar is enabled, free/busy is checked for all panel members and only slots where everyone is free are proposed.

---

## Email Notifications Setup

The app uses Python's built-in `smtplib` — no extra packages required.

1. Enable 2-Step Verification on your Google account.
2. Go to **Google Account → Security → App Passwords**.
3. Generate a password for "Mail" → "Other (HR Assistant)".
4. Copy the 16-character code (no spaces) into `.env`:

```env
EMAIL_ENABLED=true
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
EMAIL_FROM_NAME=HR AI Assistant
```

If SMTP fails, the endpoint still returns success — the error is printed to the backend terminal and `email_sent: false` is returned in the response.

---

## API Reference

### `POST /api/v1/schedule/request`

Parse candidate text and return available slots for the target week.

**Request:**
```json
{
  "raw_text": "Hi, I'm Jane Doe (jane@example.com), applying for ML Engineer.",
  "week_offset": 0
}
```

**Response:**
```json
{
  "status": "success",
  "phase": "slots_proposed",
  "candidate": {
    "candidate_name": "Jane Doe",
    "candidate_email": "jane@example.com",
    "target_role": "ML Engineer",
    "department": "Engineering",
    "is_valid": true
  },
  "proposed_slots": [
    "2026-06-30T10:00:00",
    "2026-07-02T14:00:00",
    "2026-07-04T16:00:00"
  ],
  "week_offset": 0
}
```

### `POST /api/v1/schedule/more-slots`

Return slots for a later week without re-parsing the candidate text.

**Request:**
```json
{
  "candidate_email": "jane@example.com",
  "week_offset": 1
}
```

**Response:** same shape as `/request`, without the `candidate` field.

### `POST /api/v1/schedule/confirm`

Confirm a slot, create the calendar event, and send the confirmation email.

**Request:**
```json
{
  "candidate_email": "jane@example.com",
  "selected_slot": "2026-06-30T10:00:00"
}
```

**Response:**
```json
{
  "status": "success",
  "phase": "booking_confirmed",
  "booking_metadata": {
    "event_id": "abc123xyz",
    "google_meet_url": "https://meet.google.com/xxx-yyyy-zzz",
    "attendees": ["jane@example.com", "alice@company.com"],
    "locked_slot_time": "2026-06-30T10:00:00",
    "email_sent": true
  }
}
```

---

## Database

SQLite (`interview_scheduler.db`) is created automatically on first run.

| Column | Description |
|--------|-------------|
| `id` | Auto-increment primary key |
| `name` | Candidate full name |
| `email` | Unique candidate email |
| `target_role` | Role applied for |
| `department` | Engineering or Product |
| `status` | `In Progress - Scheduling` → `Interview Scheduled` |
| `assigned_panel` | Comma-separated panel emails |
| `confirmed_slot` | ISO datetime of confirmed interview |
| `calendar_event_id` | Google Calendar event ID |

---

## Department Mapping

Claude AI maps the stated role to one of two departments:

| Department | Example Roles |
|------------|--------------|
| **Engineering** | Software Engineer, Backend, Frontend, DevOps, Data Scientist, ML Engineer, Platform, Security |
| **Product** | Product Manager, UX Designer, Business Analyst, Program Manager |

---

## Project Structure

```
Interview Scheduling system/
├── app/                          # FastAPI backend (canonical)
│   ├── main.py
│   ├── config.py
│   ├── agents/
│   │   └── parser_agent.py       # Claude AI extraction
│   ├── database/
│   │   ├── connection.py
│   │   └── models.py
│   ├── routers/
│   │   └── scheduler.py          # /request /more-slots /confirm
│   └── services/
│       ├── google_calendar.py
│       └── email_service.py      # Gmail SMTP confirmation
├── tests/                        # pytest suite (49 tests)
│   ├── conftest.py               # shared fixtures
│   ├── unit/                     # slot logic, parser, email
│   └── integration/              # API endpoint tests
├── frontend/
│   └── app.py                    # Streamlit UI
├── Dockerfile                    # Backend image (includes tests/)
├── Dockerfile.frontend           # Frontend image
├── docker-compose.yml
├── .dockerignore
├── requirements.txt
├── .env
├── CLAUDE.md                     # Claude Code project guide
└── README.md
```

---

## Technologies

| Layer | Technology |
|-------|-----------|
| AI / LLM | [Claude Haiku](https://anthropic.com) via `langchain-anthropic` |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Frontend | [Streamlit](https://streamlit.io/) |
| Database | [SQLite](https://sqlite.org/) + [SQLAlchemy](https://www.sqlalchemy.org/) |
| Calendar | [Google Calendar API](https://developers.google.com/calendar) v3 |
| Auth | Google OAuth 2.0 (InstalledAppFlow) |
| Email | Python `smtplib` + Gmail SMTP |
| Validation | [Pydantic](https://docs.pydantic.dev/) v2 |
| Containers | Docker + Docker Compose |
| Testing | pytest + pytest-cov + httpx |

---

## Troubleshooting

**"Could not extract required fields"**
The input text didn't include a recognisable name, email, or job title. Make the text more explicit.

**"Cannot reach the backend"**
Start the FastAPI server first: `uvicorn app.main:app --reload --port 8000`

**"Google OAuth credentials file not found"**
The app will fall back to local slot generation automatically. Download `credentials.json` from Google Cloud Console and place it in the project root only if you need real free/busy checking.

**No confirmation email received**
Check the backend terminal for `[EmailService] send_confirmation failed: ...`. The most common cause is using a regular Gmail password instead of a 16-character App Password.

**`ModuleNotFoundError: No module named 'app'`**
Always run `uvicorn` from the project root directory, not from inside `app/`.

**Docker: frontend can't reach backend**
Ensure both services are running (`docker compose ps`). The frontend uses `http://backend:8000` inside Docker — do not set `API_BASE` to `localhost` in the compose file.
