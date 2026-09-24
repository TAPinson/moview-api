from __future__ import annotations

import html
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr
from typing import Any


def build_calendar_invitation(
    *,
    uid: str,
    summary: str,
    starts_at: datetime,
    ends_at: datetime,
    organizer_email: str,
    attendees: list[tuple[str, str]],
    location: str | None = None,
    description: str | None = None,
    sequence: int = 0,
    created_at: datetime | None = None,
) -> str:
    if not uid.strip():
        raise RuntimeError("Calendar UID is required.")
    if not summary.strip():
        raise RuntimeError("Invitation summary is required.")
    if not organizer_email.strip():
        raise RuntimeError("Organizer email is required.")
    if not attendees:
        raise RuntimeError("At least one attendee is required.")
    if sequence < 0:
        raise RuntimeError("Calendar sequence cannot be negative.")

    starts_at = _required_aware_datetime(starts_at, "Start time")
    ends_at = _required_aware_datetime(ends_at, "End time")
    if ends_at <= starts_at:
        raise RuntimeError("Invitation end time must be after its start time.")

    created_at = _required_aware_datetime(
        created_at or datetime.now(timezone.utc),
        "Creation time",
    )

    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//Moview//Movie Invitation//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{_escape_text(uid)}",
        f"DTSTAMP:{_calendar_datetime(created_at)}",
        f"DTSTART:{_calendar_datetime(starts_at)}",
        f"DTEND:{_calendar_datetime(ends_at)}",
        f"SEQUENCE:{sequence}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        f"SUMMARY:{_escape_text(summary)}",
        f"ORGANIZER:mailto:{organizer_email}",
    ]

    for name, email_address in attendees:
        if not email_address.strip():
            raise RuntimeError("Attendee email is required.")
        lines.append(
            "ATTENDEE;"
            f"CN={_quote_parameter(name)};"
            "ROLE=REQ-PARTICIPANT;"
            "PARTSTAT=NEEDS-ACTION;"
            "RSVP=TRUE:"
            f"mailto:{email_address}"
        )

    if location:
        lines.append(f"LOCATION:{_escape_text(location)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape_text(description)}")

    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return "\r\n".join(_fold_line(line) for line in lines) + "\r\n"


def build_invitation_email(
    *,
    sender_name: str,
    sender_email: str,
    recipients: list[tuple[str, str]],
    subject: str,
    calendar_content: str,
) -> EmailMessage:
    if not sender_email.strip():
        raise RuntimeError("Invitation sender email is required.")
    if not recipients:
        raise RuntimeError("At least one email recipient is required.")

    message = EmailMessage()
    message["From"] = formataddr((sender_name, sender_email))
    message["To"] = ", ".join(
        formataddr((name, email_address))
        for name, email_address in recipients
    )
    message["Subject"] = subject
    message.set_content(
        f"{subject}\n\n"
        "A calendar invitation is attached to this message."
    )
    message.add_alternative(
        "<html><body>"
        f"<p>{html.escape(subject)}</p>"
        "<p>A calendar invitation is attached to this message.</p>"
        "</body></html>",
        subtype="html",
    )
    message.add_attachment(
        calendar_content,
        subtype="calendar",
        filename="movie-night.ics",
        params={"method": "REQUEST", "charset": "UTF-8"},
    )

    calendar_part = next(message.iter_attachments())
    calendar_part["Content-Class"] = "urn:content-classes:calendarmessage"
    return message


def send_invitation_email(
    *,
    message: EmailMessage,
    sender_email: str,
    recipient_emails: list[str],
    ses_client: Any | None = None,
) -> str:
    if ses_client is None:
        import boto3

        ses_client = boto3.client("sesv2")

    response = ses_client.send_email(
        FromEmailAddress=sender_email,
        Destination={"ToAddresses": recipient_emails},
        Content={"Raw": {"Data": message.as_bytes(policy=SMTP)}},
    )
    message_id = response.get("MessageId")
    if not message_id:
        raise RuntimeError("SES did not return a message ID.")
    return str(message_id)


def _required_aware_datetime(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError(f"{label} is required.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError(f"{label} must include a time zone.")
    return value


def _calendar_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _quote_parameter(value: str) -> str:
    escaped = (
        value.replace("^", "^^")
        .replace('"', "^'")
        .replace("\r\n", "^n")
        .replace("\n", "^n")
        .replace("\r", "^n")
    )
    return f'"{escaped}"'


def _fold_line(value: str) -> str:
    lines: list[str] = []
    current = ""
    byte_limit = 75

    for character in value:
        candidate = current + character
        if len(candidate.encode("utf-8")) > byte_limit:
            lines.append(current)
            current = " " + character
            byte_limit = 75
        else:
            current = candidate

    lines.append(current)
    return "\r\n".join(lines)
