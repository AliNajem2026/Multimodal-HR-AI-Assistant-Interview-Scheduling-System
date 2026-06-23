"""
Integration tests for all three scheduling endpoints.

All LLM (InterviewParsingAgent) and Google Calendar calls are mocked so tests
run without real API credentials. The app uses an in-memory SQLite DB via the
api_client fixture defined in conftest.py.
"""
from unittest.mock import patch, MagicMock
import pytest

from app.database.models import CandidateRecord
from tests.conftest import make_valid_context

VALID_TEXT = "Hi, I'm Jane Doe (jane@example.com), applying for Senior Backend Engineer."
VALID_SLOT = "2026-06-30T10:00:00"
CANDIDATE_EMAIL = "jane@example.com"


def _gcal_no_credentials():
    """Context manager: GoogleCalendarService raises FileNotFoundError on init."""
    return patch(
        "app.routers.scheduler.GoogleCalendarService",
        side_effect=FileNotFoundError("credentials.json not found"),
    )


def _mock_agent(context=None):
    """Context manager: InterviewParsingAgent.parse_request returns the given context."""
    ctx = context or make_valid_context()
    mock = patch("app.routers.scheduler.InterviewParsingAgent")
    return mock, ctx


# ── /request ─────────────────────────────────────────────────────────────────

class TestRequestEndpoint:
    def test_valid_text_returns_200_with_three_slots(self, api_client):
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            resp = api_client.post(
                "/api/v1/schedule/request",
                json={"raw_text": VALID_TEXT, "week_offset": 0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["phase"] == "slots_proposed"
        assert len(data["proposed_slots"]) == 3

    def test_candidate_profile_returned_in_response(self, api_client):
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            resp = api_client.post(
                "/api/v1/schedule/request",
                json={"raw_text": VALID_TEXT},
            )

        candidate = resp.json()["candidate"]
        assert candidate["candidate_name"] == "Jane Doe"
        assert candidate["candidate_email"] == CANDIDATE_EMAIL
        assert candidate["department"] == "Engineering"

    def test_invalid_extraction_returns_422(self, api_client):
        from app.agents.parser_agent import ParsedInterviewContext
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = ParsedInterviewContext(is_valid=False)
            resp = api_client.post(
                "/api/v1/schedule/request",
                json={"raw_text": "vague text with no useful info"},
            )

        assert resp.status_code == 422

    def test_candidate_record_created_in_db(self, api_client, db_session):
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            api_client.post("/api/v1/schedule/request", json={"raw_text": VALID_TEXT})

        candidate = db_session.query(CandidateRecord).filter(
            CandidateRecord.email == CANDIDATE_EMAIL
        ).first()
        assert candidate is not None
        assert candidate.name == "Jane Doe"
        assert candidate.status == "In Progress - Scheduling"
        assert candidate.department == "Engineering"

    def test_duplicate_email_upserts_existing_record(self, api_client, db_session):
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            api_client.post("/api/v1/schedule/request", json={"raw_text": VALID_TEXT})
            # Second request with the same email — should not error
            api_client.post("/api/v1/schedule/request", json={"raw_text": VALID_TEXT})

        count = db_session.query(CandidateRecord).filter(
            CandidateRecord.email == CANDIDATE_EMAIL
        ).count()
        assert count == 1, "Duplicate email should upsert, not create a second row"

    def test_week_offset_returned_in_response(self, api_client):
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            resp = api_client.post(
                "/api/v1/schedule/request",
                json={"raw_text": VALID_TEXT, "week_offset": 2},
            )

        assert resp.json()["week_offset"] == 2

    def test_week_offset_1_returns_later_slots_than_offset_0(self, api_client):
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            resp_0 = api_client.post(
                "/api/v1/schedule/request",
                json={"raw_text": VALID_TEXT, "week_offset": 0},
            )
            resp_1 = api_client.post(
                "/api/v1/schedule/request",
                json={"raw_text": VALID_TEXT, "week_offset": 1},
            )

        slot_0 = resp_0.json()["proposed_slots"][0]
        slot_1 = resp_1.json()["proposed_slots"][0]
        assert slot_1 > slot_0

    def test_negative_week_offset_rejected_by_pydantic(self, api_client):
        resp = api_client.post(
            "/api/v1/schedule/request",
            json={"raw_text": VALID_TEXT, "week_offset": -1},
        )
        assert resp.status_code == 422


# ── /more-slots ───────────────────────────────────────────────────────────────

class TestMoreSlotsEndpoint:
    @pytest.fixture(autouse=True)
    def seed_candidate(self, api_client):
        """Create the candidate record via /request before each test in this class."""
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            api_client.post("/api/v1/schedule/request", json={"raw_text": VALID_TEXT})

    def test_valid_request_returns_200_with_slots(self, api_client):
        with _gcal_no_credentials():
            resp = api_client.post(
                "/api/v1/schedule/more-slots",
                json={"candidate_email": CANDIDATE_EMAIL, "week_offset": 1},
            )

        assert resp.status_code == 200
        assert len(resp.json()["proposed_slots"]) == 3

    def test_week_offset_reflected_in_response(self, api_client):
        with _gcal_no_credentials():
            resp = api_client.post(
                "/api/v1/schedule/more-slots",
                json={"candidate_email": CANDIDATE_EMAIL, "week_offset": 3},
            )

        assert resp.json()["week_offset"] == 3

    def test_unknown_candidate_returns_404(self, api_client):
        with _gcal_no_credentials():
            resp = api_client.post(
                "/api/v1/schedule/more-slots",
                json={"candidate_email": "nobody@example.com", "week_offset": 1},
            )

        assert resp.status_code == 404

    def test_week_offset_zero_rejected_by_pydantic(self, api_client):
        resp = api_client.post(
            "/api/v1/schedule/more-slots",
            json={"candidate_email": CANDIDATE_EMAIL, "week_offset": 0},
        )
        assert resp.status_code == 422

    def test_slots_are_further_in_future_than_initial_request(self, api_client):
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            initial_resp = api_client.post(
                "/api/v1/schedule/request",
                json={"raw_text": VALID_TEXT, "week_offset": 0},
            )

        with _gcal_no_credentials():
            next_resp = api_client.post(
                "/api/v1/schedule/more-slots",
                json={"candidate_email": CANDIDATE_EMAIL, "week_offset": 1},
            )

        first_slot = initial_resp.json()["proposed_slots"][0]
        next_slot = next_resp.json()["proposed_slots"][0]
        assert next_slot > first_slot


# ── /confirm ──────────────────────────────────────────────────────────────────

class TestConfirmEndpoint:
    @pytest.fixture(autouse=True)
    def seed_candidate(self, api_client):
        """Create the candidate record via /request before each test in this class."""
        with patch("app.routers.scheduler.InterviewParsingAgent") as mock_cls, \
             _gcal_no_credentials():
            mock_cls.return_value.parse_request.return_value = make_valid_context()
            api_client.post("/api/v1/schedule/request", json={"raw_text": VALID_TEXT})

    def test_valid_confirm_returns_201(self, api_client):
        with _gcal_no_credentials(), \
             patch("app.routers.scheduler.EmailService") as mock_email:
            mock_email.return_value.send_confirmation.return_value = False
            resp = api_client.post(
                "/api/v1/schedule/confirm",
                json={"candidate_email": CANDIDATE_EMAIL, "selected_slot": VALID_SLOT},
            )

        assert resp.status_code == 201

    def test_response_contains_booking_metadata(self, api_client):
        with _gcal_no_credentials(), \
             patch("app.routers.scheduler.EmailService") as mock_email:
            mock_email.return_value.send_confirmation.return_value = False
            resp = api_client.post(
                "/api/v1/schedule/confirm",
                json={"candidate_email": CANDIDATE_EMAIL, "selected_slot": VALID_SLOT},
            )

        meta = resp.json()["booking_metadata"]
        assert "event_id" in meta
        assert "google_meet_url" in meta
        assert meta["locked_slot_time"] == VALID_SLOT
        assert CANDIDATE_EMAIL in meta["attendees"]

    def test_fallback_event_id_used_when_no_google_credentials(self, api_client):
        with _gcal_no_credentials(), \
             patch("app.routers.scheduler.EmailService") as mock_email:
            mock_email.return_value.send_confirmation.return_value = False
            resp = api_client.post(
                "/api/v1/schedule/confirm",
                json={"candidate_email": CANDIDATE_EMAIL, "selected_slot": VALID_SLOT},
            )

        event_id = resp.json()["booking_metadata"]["event_id"]
        assert event_id.startswith("local-event-")

    def test_candidate_status_updated_to_scheduled(self, api_client, db_session):
        with _gcal_no_credentials(), \
             patch("app.routers.scheduler.EmailService") as mock_email:
            mock_email.return_value.send_confirmation.return_value = False
            api_client.post(
                "/api/v1/schedule/confirm",
                json={"candidate_email": CANDIDATE_EMAIL, "selected_slot": VALID_SLOT},
            )

        # Expire the session cache to force a fresh DB read
        db_session.expire_all()
        candidate = db_session.query(CandidateRecord).filter(
            CandidateRecord.email == CANDIDATE_EMAIL
        ).first()
        assert candidate.status == "Interview Scheduled"
        assert candidate.confirmed_slot == VALID_SLOT

    def test_unknown_candidate_returns_404(self, api_client):
        with _gcal_no_credentials():
            resp = api_client.post(
                "/api/v1/schedule/confirm",
                json={"candidate_email": "nobody@example.com", "selected_slot": VALID_SLOT},
            )

        assert resp.status_code == 404

    def test_email_sent_flag_is_false_when_email_disabled(self, api_client):
        with _gcal_no_credentials(), \
             patch("app.routers.scheduler.settings") as mock_settings:
            mock_settings.EMAIL_ENABLED = False
            resp = api_client.post(
                "/api/v1/schedule/confirm",
                json={"candidate_email": CANDIDATE_EMAIL, "selected_slot": VALID_SLOT},
            )

        assert resp.json()["booking_metadata"]["email_sent"] is False

    def test_email_sent_flag_is_true_when_email_succeeds(self, api_client):
        with _gcal_no_credentials(), \
             patch("app.routers.scheduler.settings") as mock_settings, \
             patch("app.routers.scheduler.EmailService") as mock_email:
            mock_settings.EMAIL_ENABLED = True
            mock_email.return_value.send_confirmation.return_value = True
            resp = api_client.post(
                "/api/v1/schedule/confirm",
                json={"candidate_email": CANDIDATE_EMAIL, "selected_slot": VALID_SLOT},
            )

        assert resp.json()["booking_metadata"]["email_sent"] is True

    def test_google_calendar_503_propagates_to_client(self, api_client):
        with patch(
            "app.routers.scheduler.GoogleCalendarService",
            side_effect=RuntimeError("Calendar quota exceeded"),
        ):
            resp = api_client.post(
                "/api/v1/schedule/confirm",
                json={"candidate_email": CANDIDATE_EMAIL, "selected_slot": VALID_SLOT},
            )

        assert resp.status_code == 503


# ── Health check ──────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_root_returns_200(self, api_client):
        resp = api_client.get("/")
        assert resp.status_code == 200
        assert resp.json()["system_status"] == "Operational"
