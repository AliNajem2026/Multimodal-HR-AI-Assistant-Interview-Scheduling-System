import smtplib
from unittest.mock import patch, MagicMock, call
import pytest
from app.services.email_service import EmailService


def _make_service() -> EmailService:
    """Build an EmailService with test SMTP credentials without reading .env."""
    svc = object.__new__(EmailService)
    svc.host = "smtp.gmail.com"
    svc.port = 587
    svc.user = "test@gmail.com"
    svc.password = "testapppassword"
    svc.from_name = "HR AI Assistant"
    return svc


SLOT_ISO = "2026-06-29T10:00:00"
MEET_URL = "https://meet.google.com/test-link"


class TestSendConfirmation:
    def test_returns_true_on_successful_smtp(self):
        svc = _make_service()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            result = svc.send_confirmation(
                candidate_name="Jane Doe",
                candidate_email="jane@example.com",
                target_role="Backend Engineer",
                slot_iso=SLOT_ISO,
                meet_url=MEET_URL,
            )

        assert result is True

    def test_calls_starttls_and_login(self):
        svc = _make_service()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            svc.send_confirmation(
                candidate_name="Jane Doe",
                candidate_email="jane@example.com",
                target_role="Backend Engineer",
                slot_iso=SLOT_ISO,
                meet_url=MEET_URL,
            )

        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@gmail.com", "testapppassword")

    def test_sendmail_targets_candidate_email(self):
        svc = _make_service()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            svc.send_confirmation(
                candidate_name="Jane Doe",
                candidate_email="jane@example.com",
                target_role="Backend Engineer",
                slot_iso=SLOT_ISO,
                meet_url=MEET_URL,
            )

        args = mock_server.sendmail.call_args[0]
        assert args[1] == "jane@example.com"

    def test_returns_false_on_smtp_auth_error(self):
        svc = _make_service()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            result = svc.send_confirmation(
                candidate_name="Jane Doe",
                candidate_email="jane@example.com",
                target_role="Backend Engineer",
                slot_iso=SLOT_ISO,
                meet_url=MEET_URL,
            )

        assert result is False

    def test_returns_false_on_connection_error(self):
        svc = _make_service()
        with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("SMTP down")):
            result = svc.send_confirmation(
                candidate_name="Jane Doe",
                candidate_email="jane@example.com",
                target_role="Backend Engineer",
                slot_iso=SLOT_ISO,
                meet_url=MEET_URL,
            )

        assert result is False

    def test_subject_contains_role(self):
        import email as stdlib_email
        import email.header

        svc = _make_service()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            svc.send_confirmation(
                candidate_name="Jane Doe",
                candidate_email="jane@example.com",
                target_role="ML Engineer",
                slot_iso=SLOT_ISO,
                meet_url=MEET_URL,
            )

        raw_message = mock_server.sendmail.call_args[0][2]
        msg = stdlib_email.message_from_string(raw_message)
        # Decode MIME-encoded subject (e.g. =?utf-8?q?...?=)
        decoded_parts = email.header.decode_header(msg["Subject"])
        subject = "".join(
            part.decode(enc or "utf-8") if isinstance(part, bytes) else part
            for part, enc in decoded_parts
        )
        assert "ML Engineer" in subject


class TestFormatSlot:
    def test_iso_string_becomes_human_readable(self):
        result = EmailService._format_slot("2026-06-29T10:00:00")
        assert "2026" in result
        assert "10:00" in result

    def test_invalid_iso_returns_original_string(self):
        bad = "not-a-date"
        assert EmailService._format_slot(bad) == bad

    def test_monday_label_in_formatted_output(self):
        # 2026-06-29 is a Monday
        result = EmailService._format_slot("2026-06-29T10:00:00")
        assert "Monday" in result
