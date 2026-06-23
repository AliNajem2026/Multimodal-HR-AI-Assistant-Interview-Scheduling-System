import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session
from typing import List

from app.config import settings
from app.database.connection import get_db
from app.database.models import CandidateRecord
from app.agents.parser_agent import InterviewParsingAgent
from app.services.google_calendar import GoogleCalendarService
from app.services.email_service import EmailService

router = APIRouter(prefix="/api/v1/schedule", tags=["Interview Scheduling"])

PANEL_DIRECTORY = {
    "Engineering": ["alice@hotmail.com", "John@gmail.com", "ALI@gmail.com"],
    "Product": ["charlie@gmail.com", "evan@company.com"],
}


class RawPayload(BaseModel):
    raw_text: str = Field(..., description="Unstructured candidate email or form text.")
    week_offset: int = Field(default=0, ge=0, description="0 = next Mon–Fri, 1 = week after, etc.")


class BookingConfirmationPayload(BaseModel):
    candidate_email: EmailStr
    selected_slot: str


class MoreSlotsPayload(BaseModel):
    candidate_email: EmailStr
    week_offset: int = Field(default=1, ge=1, description="Week offset (≥1) for next-week proposals.")


def _generate_week_slots(week_offset: int = 0) -> List[str]:
    """Return 3 slots spread across Mon/Wed/Fri of the target week at 10 AM / 2 PM / 4 PM.

    week_offset=0 → next calendar week, week_offset=1 → the week after, etc.
    """
    today = datetime.date.today()
    days_to_monday = (7 - today.weekday()) % 7 or 7
    week_monday = today + datetime.timedelta(days=days_to_monday + week_offset * 7)

    slot_plan = [
        (0, 10),  # Monday    10:00 AM
        (2, 14),  # Wednesday  2:00 PM
        (4, 16),  # Friday     4:00 PM
    ]

    return [
        datetime.datetime.combine(
            week_monday + datetime.timedelta(days=day_offset),
            datetime.time(hour, 0),
        ).isoformat()
        for day_offset, hour in slot_plan
    ]


def _week_label(offset: int) -> str:
    if offset == 0:
        return "next week"
    if offset == 1:
        return "the week after next"
    return f"{offset + 1} weeks from now"


def _get_slots(panel: List[str], week_offset: int) -> List[str]:
    """Try Google Calendar first; fall back to local date generator if credentials are absent."""
    try:
        gcal = GoogleCalendarService()
        return gcal.query_free_busy(panel_emails=panel, week_offset=week_offset)
    except FileNotFoundError:
        return _generate_week_slots(week_offset)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Google Calendar error: {exc}",
        )


@router.post("/request", status_code=status.HTTP_200_OK)
async def handle_scheduling_request(payload: RawPayload, db: Session = Depends(get_db)):
    agent = InterviewParsingAgent()
    parsed_context = agent.parse_request(payload.raw_text)

    if not parsed_context.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Could not extract required fields (name, email, department) from the text. "
                "Please ensure the input includes the candidate's full name, email address, "
                "and the role they are applying for."
            ),
        )

    panel = PANEL_DIRECTORY.get(parsed_context.department, PANEL_DIRECTORY["Engineering"])
    computed_slots = _get_slots(panel, payload.week_offset)

    existing = db.query(CandidateRecord).filter(
        CandidateRecord.email == parsed_context.candidate_email
    ).first()
    if existing:
        db.delete(existing)
        db.commit()

    db.add(CandidateRecord(
        name=parsed_context.candidate_name,
        email=parsed_context.candidate_email,
        target_role=parsed_context.target_role,
        department=parsed_context.department,
        assigned_panel=",".join(panel),
        status="In Progress - Scheduling",
    ))
    db.commit()

    return {
        "status": "success",
        "phase": "slots_proposed",
        "candidate": parsed_context,
        "proposed_slots": computed_slots,
        "week_offset": payload.week_offset,
    }


@router.post("/more-slots", status_code=status.HTTP_200_OK)
async def get_more_slots(payload: MoreSlotsPayload, db: Session = Depends(get_db)):
    """Return slots for a later week when the candidate declines the current proposals."""
    candidate = db.query(CandidateRecord).filter(
        CandidateRecord.email == payload.candidate_email
    ).first()

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found. Please restart the scheduling request.",
        )

    panel = candidate.assigned_panel.split(",")
    computed_slots = _get_slots(panel, payload.week_offset)

    return {
        "status": "success",
        "phase": "slots_proposed",
        "proposed_slots": computed_slots,
        "week_offset": payload.week_offset,
    }


@router.post("/confirm", status_code=status.HTTP_201_CREATED)
async def finalize_interview_booking(
    payload: BookingConfirmationPayload, db: Session = Depends(get_db)
):
    candidate = db.query(CandidateRecord).filter(
        CandidateRecord.email == payload.candidate_email
    ).first()

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found. Please restart the scheduling request.",
        )

    panel_list = candidate.assigned_panel.split(",")

    try:
        gcal = GoogleCalendarService()
        event_details = gcal.create_interview_event(
            candidate_name=candidate.name,
            candidate_email=candidate.email,
            panel_emails=panel_list,
            start_iso_time=payload.selected_slot,
        )
    except FileNotFoundError:
        event_details = {
            "event_id": f"local-event-{int(datetime.datetime.now().timestamp())}",
            "meet_link": "https://meet.google.com/placeholder-link",
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Google Calendar error: {exc}")

    candidate.status = "Interview Scheduled"
    candidate.confirmed_slot = payload.selected_slot
    candidate.calendar_event_id = event_details["event_id"]
    db.commit()

    email_sent = False
    if settings.EMAIL_ENABLED:
        svc = EmailService()
        email_sent = svc.send_confirmation(
            candidate_name=candidate.name,
            candidate_email=candidate.email,
            target_role=candidate.target_role,
            slot_iso=payload.selected_slot,
            meet_url=event_details["meet_link"],
        )

    return {
        "status": "success",
        "phase": "booking_confirmed",
        "booking_metadata": {
            "event_id": event_details["event_id"],
            "google_meet_url": event_details["meet_link"],
            "attendees": [candidate.email] + panel_list,
            "locked_slot_time": payload.selected_slot,
            "email_sent": email_sent,
        },
    }
