import smtplib
import datetime
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings


class EmailService:
    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_name = settings.EMAIL_FROM_NAME

    def _send(self, to: str, subject: str, body_html: str, body_text: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.user}>"
        msg["To"] = to
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(self.host, self.port) as server:
            server.starttls()
            server.login(self.user, self.password)
            server.sendmail(self.user, to, msg.as_string())

    @staticmethod
    def _format_slot(iso: str) -> str:
        try:
            dt = datetime.datetime.fromisoformat(iso)
            return dt.strftime("%A, %b %d %Y · %I:%M %p")
        except ValueError:
            return iso

    def send_confirmation(
        self,
        candidate_name: str,
        candidate_email: str,
        target_role: str,
        slot_iso: str,
        meet_url: str,
    ) -> bool:
        """Email the candidate confirming the booked interview slot. Returns True on success."""
        formatted_slot = self._format_slot(slot_iso)
        subject = f"Interview Confirmed — {target_role}"

        body_text = (
            f"Hi {candidate_name},\n\n"
            f"Your interview for the {target_role} position has been confirmed.\n\n"
            f"  Date & Time : {formatted_slot}\n"
            f"  Google Meet : {meet_url}\n\n"
            f"Please join the meeting link at the scheduled time. "
            f"We look forward to speaking with you!\n\n"
            f"Best regards,\n{self.from_name}"
        )

        body_html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#1e293b">
          <h2 style="color:#22c55e">Interview Confirmed — {target_role}</h2>
          <p>Hi <strong>{candidate_name}</strong>,</p>
          <p>Your interview for the <strong>{target_role}</strong> position has been confirmed.</p>
          <table style="background:#f1f5f9;border-radius:8px;padding:16px;width:100%;border-collapse:collapse">
            <tr>
              <td style="padding:6px 12px;font-weight:bold;white-space:nowrap">📅 Date &amp; Time</td>
              <td style="padding:6px 12px">{formatted_slot}</td>
            </tr>
            <tr>
              <td style="padding:6px 12px;font-weight:bold;white-space:nowrap">🎥 Google Meet</td>
              <td style="padding:6px 12px">
                <a href="{meet_url}" style="color:#0ea5e9">{meet_url}</a>
              </td>
            </tr>
          </table>
          <p>Please join the meeting link at the scheduled time. We look forward to speaking with you!</p>
          <p>Best regards,<br><strong>{self.from_name}</strong></p>
        </div>
        """

        try:
            self._send(candidate_email, subject, body_html, body_text)
            return True
        except Exception as exc:
            print(f"[EmailService] send_confirmation failed: {exc}", file=sys.stderr, flush=True)
            return False
