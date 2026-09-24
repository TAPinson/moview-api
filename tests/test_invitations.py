from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser

import pytest

from moview_api.invitations import (
    build_calendar_invitation,
    build_invitation_email,
    send_invitation_email,
)


STARTS_AT = datetime(2026, 10, 3, 23, 30, tzinfo=timezone.utc)
ENDS_AT = STARTS_AT + timedelta(minutes=150)
CREATED_AT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def test_build_calendar_invitation() -> None:
    invitation = build_calendar_invitation(
        uid="invitation-42@moview.example",
        summary="Watch Dune, Part Two",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        organizer_email="movie-night@moview.example",
        attendees=[
            ("Ali Example", "ali@example.com"),
            ("Friendly User", "friend@example.com"),
        ],
        location="Ali's house; living room",
        description="Bring snacks\nDoors open at 7.",
        created_at=CREATED_AT,
    )

    assert invitation.startswith("BEGIN:VCALENDAR\r\n")
    assert invitation.endswith("END:VCALENDAR\r\n")
    assert "METHOD:REQUEST\r\n" in invitation
    assert "UID:invitation-42@moview.example\r\n" in invitation
    assert "DTSTAMP:20260922T120000Z\r\n" in invitation
    assert "DTSTART:20261003T233000Z\r\n" in invitation
    assert "DTEND:20261004T020000Z\r\n" in invitation
    assert "SUMMARY:Watch Dune\\, Part Two\r\n" in invitation
    assert "LOCATION:Ali's house\\; living room\r\n" in invitation
    assert "DESCRIPTION:Bring snacks\\nDoors open at 7.\r\n" in invitation
    assert invitation.count("ATTENDEE;") == 2


def test_build_calendar_invitation_requires_timezone() -> None:
    with pytest.raises(RuntimeError, match="Start time must include a time zone"):
        build_calendar_invitation(
            uid="invitation-42@moview.example",
            summary="Watch Dune",
            starts_at=datetime(2026, 10, 3, 19, 30),
            ends_at=ENDS_AT,
            organizer_email="movie-night@moview.example",
            attendees=[("Ali", "ali@example.com")],
        )


def test_build_calendar_invitation_requires_end_after_start() -> None:
    with pytest.raises(RuntimeError, match="end time must be after"):
        build_calendar_invitation(
            uid="invitation-42@moview.example",
            summary="Watch Dune",
            starts_at=STARTS_AT,
            ends_at=STARTS_AT,
            organizer_email="movie-night@moview.example",
            attendees=[("Ali", "ali@example.com")],
        )


def test_build_invitation_email_attaches_calendar() -> None:
    calendar_content = build_calendar_invitation(
        uid="invitation-42@moview.example",
        summary="Watch Dune",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        organizer_email="movie-night@moview.example",
        attendees=[("Ali", "ali@example.com")],
        created_at=CREATED_AT,
    )

    message = build_invitation_email(
        sender_name="Moview",
        sender_email="movie-night@moview.example",
        recipients=[("Ali", "ali@example.com")],
        subject="Movie night: Dune",
        calendar_content=calendar_content,
    )

    parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    attachments = list(parsed.iter_attachments())

    assert parsed["From"] == "Moview <movie-night@moview.example>"
    assert parsed["To"] == "Ali <ali@example.com>"
    assert parsed["Subject"] == "Movie night: Dune"
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "text/calendar"
    assert attachments[0].get_param("method") == "REQUEST"
    assert attachments[0].get_filename() == "movie-night.ics"
    assert "BEGIN:VCALENDAR" in attachments[0].get_content()


class FakeSesClient:
    def __init__(self) -> None:
        self.request = None

    def send_email(self, **kwargs):
        self.request = kwargs
        return {"MessageId": "ses-message-123"}


def test_send_invitation_email() -> None:
    message = build_invitation_email(
        sender_name="Moview",
        sender_email="movie-night@moview.example",
        recipients=[("Ali", "ali@example.com")],
        subject="Movie night: Dune",
        calendar_content="BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
    )
    ses_client = FakeSesClient()

    message_id = send_invitation_email(
        message=message,
        sender_email="movie-night@moview.example",
        recipient_emails=["ali@example.com"],
        ses_client=ses_client,
    )

    assert message_id == "ses-message-123"
    assert ses_client.request["FromEmailAddress"] == (
        "movie-night@moview.example"
    )
    assert ses_client.request["Destination"] == {
        "ToAddresses": ["ali@example.com"]
    }
    assert b"Content-Type: text/calendar" in (
        ses_client.request["Content"]["Raw"]["Data"]
    )
