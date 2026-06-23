import os
import datetime
from typing import List, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarService:
    def __init__(self):
        self.creds = None
        token_path = "token.json"

        if os.path.exists(token_path):
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not os.path.exists(settings.GOOGLE_CREDENTIALS_FILE):
                    raise FileNotFoundError(
                        f"Google OAuth credentials file not found: '{settings.GOOGLE_CREDENTIALS_FILE}'. "
                        "Download it from Google Cloud Console → APIs & Services → Credentials "
                        "and place it in the project root. Or set USE_MOCK_CALENDAR=true in .env "
                        "to run without Google Calendar."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    settings.GOOGLE_CREDENTIALS_FILE, SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            with open(token_path, "w") as token:
                token.write(self.creds.to_json())

        self.service = build("calendar", "v3", credentials=self.creds)

    def query_free_busy(self, panel_emails: List[str], week_offset: int = 0) -> List[str]:
        """Query Google Calendar free/busy for the target week and return up to 3 open 45-min slots.

        week_offset=0 → next Mon–Fri, week_offset=1 → the week after, etc.
        """
        today = datetime.date.today()
        days_to_monday = (7 - today.weekday()) % 7 or 7
        week_monday = today + datetime.timedelta(days=days_to_monday + week_offset * 7)
        week_friday_end = week_monday + datetime.timedelta(days=5)

        time_min = datetime.datetime.combine(
            week_monday, datetime.time(0, 0), tzinfo=datetime.timezone.utc
        ).isoformat()
        time_max = datetime.datetime.combine(
            week_friday_end, datetime.time(0, 0), tzinfo=datetime.timezone.utc
        ).isoformat()

        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": email} for email in panel_emails],
        }

        fb_response = self.service.freebusy().query(body=body).execute()
        calendars = fb_response.get("calendars", {})

        busy_intervals: List[tuple] = []
        for cal_data in calendars.values():
            for busy in cal_data.get("busy", []):
                start = datetime.datetime.fromisoformat(busy["start"].replace("Z", "+00:00"))
                end = datetime.datetime.fromisoformat(busy["end"].replace("Z", "+00:00"))
                busy_intervals.append((start, end))

        # Check Mon/Wed/Fri at 10 AM, 2 PM, 4 PM — same pattern as the fallback generator
        slot_plan = [(0, 10), (2, 14), (4, 16)]
        available_slots: List[str] = []
        for day_offset, hour in slot_plan:
            slot_date = week_monday + datetime.timedelta(days=day_offset)
            slot_start = datetime.datetime.combine(
                slot_date, datetime.time(hour, 0), tzinfo=datetime.timezone.utc
            )
            slot_end = slot_start + datetime.timedelta(minutes=45)

            is_free = all(
                not (slot_start < b_end and slot_end > b_start)
                for b_start, b_end in busy_intervals
            )
            if is_free:
                available_slots.append(slot_start.replace(tzinfo=None).isoformat())

        return available_slots

    def create_interview_event(
        self,
        candidate_name: str,
        candidate_email: str,
        panel_emails: List[str],
        start_iso_time: str,
    ) -> Dict[str, Any]:
        """Create a Google Calendar event with a Meet link for all attendees."""
        start_time = datetime.datetime.fromisoformat(start_iso_time)
        end_time = start_time + datetime.timedelta(minutes=45)

        attendees = [{"email": candidate_email}] + [
            {"email": email} for email in panel_emails
        ]

        event_body = {
            "summary": f"Technical Panel Interview: {candidate_name}",
            "description": (
                "Automated interview scheduled via the Multimodal HR AI Assistant."
            ),
            "start": {"dateTime": start_time.isoformat() + "Z", "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat() + "Z", "timeZone": "UTC"},
            "attendees": attendees,
            "conferenceData": {
                "createRequest": {
                    "requestId": f"req-{int(start_time.timestamp())}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        created_event = self.service.events().insert(
            calendarId="primary",
            body=event_body,
            conferenceDataVersion=1,
        ).execute()

        entry_points = (
            created_event.get("conferenceData", {}).get("entryPoints", [{}])
        )
        meet_link = next(
            (ep.get("uri") for ep in entry_points if ep.get("entryPointType") == "video"),
            "https://meet.google.com",
        )

        return {
            "event_id": created_event.get("id"),
            "meet_link": meet_link,
        }
