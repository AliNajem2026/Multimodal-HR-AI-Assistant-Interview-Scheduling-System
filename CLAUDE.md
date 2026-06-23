# CLAUDE.md — Interview Scheduling System

## Project overview

End-to-end agentic HR app: a recruiter pastes a candidate's raw email into a Streamlit UI, Claude AI parses it, real-time calendar slots are proposed across different days/times, the recruiter confirms one, and a Google Calendar event + confirmation email are created automatically.

## Run commands

```bash
# Terminal 1 — backend (always run from the project root)
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
streamlit run frontend/app.py
```

Docker alternative:
```bash
docker compose up --build
```

## Tests

```bash
# Run full suite (49 tests, ~0.5 s, no credentials needed)
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Single file
pytest tests/unit/test_slot_generation.py -v

# Inside Docker
docker compose run --rm test
```

All external I/O (Claude API, Google Calendar, SMTP) is mocked via `unittest.mock.patch` — tests never make real network calls.

## Canonical package layout

```
app/                        ← FastAPI backend (canonical — do NOT edit backend/)
  main.py                   ← App entrypoint, CORS, DB table creation
  config.py                 ← All settings read from .env via os.getenv()
  agents/
    parser_agent.py         ← Claude Haiku (claude-haiku-4-5-20251001) structured extraction
  database/
    connection.py           ← SQLAlchemy engine + get_db() dependency
    models.py               ← CandidateRecord ORM model
  routers/
    scheduler.py            ← POST /request  /more-slots  /confirm
  services/
    google_calendar.py      ← OAuth + free/busy query + event creation
    email_service.py        ← Gmail SMTP confirmation email (stdlib only)
frontend/
  app.py                    ← Streamlit 3-phase UI
tests/
  conftest.py               ← StaticPool in-memory SQLite engine, db_session, api_client, make_valid_context()
  unit/
    test_slot_generation.py ← Pure logic: _generate_week_slots(), _week_label()
    test_parser_agent.py    ← Mocked chain.invoke: valid/invalid/exception paths
    test_email_service.py   ← Mocked smtplib.SMTP: send, auth error, connection error
  integration/
    test_scheduler_api.py   ← All 3 endpoints via TestClient (22 tests)
backend/                    ← Legacy scaffolding — superseded, do not edit
```

## Key environment variables (.env)

| Variable | Purpose | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key | Yes |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to `credentials.json` | No — auto-generates slots if missing |
| `DATABASE_URL` | SQLite path | No — defaults to `./interview_scheduler.db` |
| `EMAIL_ENABLED` | Enable Gmail SMTP emails | No — defaults to `false` |
| `SMTP_USER` | Gmail address | Only if EMAIL_ENABLED=true |
| `SMTP_PASSWORD` | Gmail App Password (16 chars) | Only if EMAIL_ENABLED=true |
| `API_BASE` | Backend URL for frontend | No — defaults to `http://127.0.0.1:8000/api/v1/schedule` |

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/schedule/request` | Parse candidate text → return 3 slots for a given week |
| POST | `/api/v1/schedule/more-slots` | Return slots for next week (no re-parsing) |
| POST | `/api/v1/schedule/confirm` | Book slot → create Calendar event → send confirmation email |

## Slot generation logic

`_generate_week_slots(week_offset)` in `scheduler.py`:
- `week_offset=0` → next Monday's week, `week_offset=1` → week after, etc.
- Always returns Mon 10 AM / Wed 2 PM / Fri 4 PM of the target week
- Used as fallback when `credentials.json` is absent; Google Calendar uses the same Mon/Wed/Fri pattern when credentials are present

`_get_slots()` tries `GoogleCalendarService.query_free_busy()` first, catches `FileNotFoundError` (missing credentials), falls back to `_generate_week_slots()`. Any other Google error raises HTTP 503.

## Panel directory

Hardcoded in `app/routers/scheduler.py`:

```python
PANEL_DIRECTORY = {
    "Engineering": ["email1@...", "email2@...", "email3@..."],
    "Product": ["email4@...", "email5@..."],
}
```

To add a department or change panel members, edit this dict. The free/busy query checks all members in the panel list.

## Department mapping (Claude AI)

Claude Haiku maps roles to exactly `"Engineering"` or `"Product"`.
- Engineering: Software Engineer, Backend, Frontend, DevOps, Data Scientist, ML Engineer, Platform, Security
- Product: Product Manager, UX Designer, Business Analyst, Program Manager

The mapping prompt is in `app/agents/parser_agent.py`. Edit the system prompt there to change mapping rules.

## Email notifications

`EmailService` (`app/services/email_service.py`) uses Python stdlib `smtplib` — no new packages needed.

- Only one email is sent: **confirmation email** after `/confirm` succeeds
- Controlled by `EMAIL_ENABLED` in `.env`
- Gmail requires a 16-character **App Password** (not the regular Gmail password): Google Account → Security → 2-Step Verification → App Passwords
- SMTP errors are printed to stderr and do not fail the endpoint (`email_sent: bool` is returned in the response)

## Google Calendar setup

1. Google Cloud Console → enable **Google Calendar API**
2. APIs & Services → Credentials → OAuth 2.0 Client ID → Desktop app
3. Download JSON → save as `credentials.json` in project root
4. On first run: browser opens for OAuth consent → `token.json` is saved
5. Set `GOOGLE_APPLICATION_CREDENTIALS=credentials.json` in `.env`

Without `credentials.json` the app still works using the local slot generator.

## Docker

```bash
# Build and start both services
docker compose up --build

# Backend only
docker compose up backend

# Rebuild after dependency changes
docker compose up --build --force-recreate
```

- Backend image: `Dockerfile` (port 8000)
- Frontend image: `Dockerfile.frontend` (port 8501)
- SQLite data is persisted in the `db_data` named volume
- Mount `credentials.json` and `token.json` by uncommenting the volume lines in `docker-compose.yml`
- The frontend container sets `API_BASE=http://backend:8000/api/v1/schedule` automatically

## Common tasks

**Add a new department panel:**
Edit `PANEL_DIRECTORY` in `scheduler.py` and update the Claude mapping prompt in `parser_agent.py`.

**Change slot times:**
Edit `slot_plan` in `_generate_week_slots()` (scheduler.py) and in `query_free_busy()` (google_calendar.py) — keep them in sync.

**Change interview duration:**
Edit `timedelta(minutes=45)` in `google_calendar.py → create_interview_event()`.

**View the database:**
```bash
sqlite3 interview_scheduler.db ".headers on" ".mode column" "SELECT * FROM candidates;"
```

**Reset the database:**
```bash
rm interview_scheduler.db  # recreated automatically on next backend start
```

**Run a specific test class or file:**
```bash
pytest tests/integration/test_scheduler_api.py::TestConfirmEndpoint -v
pytest tests/unit/test_email_service.py -v
```

**Add a new test for a new endpoint:**
Follow the pattern in `tests/integration/test_scheduler_api.py` — use `patch('app.routers.scheduler.GoogleCalendarService', side_effect=FileNotFoundError)` to skip credentials and `patch('app.routers.scheduler.InterviewParsingAgent')` to skip the LLM.

## Known constraints

- `backend/` directory is legacy scaffolding — do not import from it or edit it
- Always run `uvicorn` from the **project root**, not from inside `app/`
- SQLite is single-writer; not suitable for concurrent production load — switch to PostgreSQL via `DATABASE_URL` if scaling
- Google OAuth token (`token.json`) must be manually refreshed if revoked or expired
