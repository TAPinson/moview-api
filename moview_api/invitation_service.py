from __future__ import annotations

import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from moview_api.db import (
    create_movie_invitation,
    mark_movie_invitation_failed,
    mark_movie_invitation_sent,
)
from moview_api.invitations import (
    build_calendar_invitation,
    build_invitation_email,
    send_invitation_email,
)
from moview_api.tmdb import get_movie_details


MINIMUM_DURATION_MINUTES = 15
MAXIMUM_DURATION_MINUTES = 480


def schedule_movie_invitation(
    *,
    user_uuid: str,
    email: str,
    input: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    friend_user_id = _positive_integer(input.get("friendUserId"), "Friend")
    movie_id = _positive_integer(input.get("movieId"), "Movie")
    starts_at = _parse_datetime(input.get("startsAt"))
    timezone_name = _timezone_name(input.get("timezone"))
    duration_minutes = _duration(input.get("durationMinutes"))
    idempotency_key = _required_text(
        input.get("idempotencyKey"),
        "Idempotency key",
        255,
    )
    location = _optional_text(input.get("location"), "Location", 500)
    message = _optional_text(input.get("message"), "Message", 2000)

    if starts_at <= now:
        raise RuntimeError("Invitation start time must be in the future.")

    ends_at = starts_at + timedelta(minutes=duration_minutes)
    movie = get_movie_details(movie_id)
    title = movie.get("title") or movie.get("original_title")
    if not isinstance(title, str) or not title.strip():
        raise RuntimeError("Movie details did not include a title.")

    sender_email = os.environ.get("MOVIEW_INVITATION_SENDER_EMAIL")
    if not sender_email:
        raise RuntimeError("Movie invitation email is not configured.")

    invitation = create_movie_invitation(
        user_uuid=user_uuid,
        email=email,
        friend_user_id=friend_user_id,
        movie_id=movie_id,
        uid=f"{uuid4()}@moview",
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=timezone_name,
        event_summary=f"Watch {title.strip()}",
        location=location,
        message=message,
        idempotency_key=idempotency_key,
    )

    if invitation["status"] == "sent":
        return _public_invitation(invitation)

    sender = invitation["sender"]
    friend = invitation["friend"]
    recipients = [
        (_participant_name(sender), sender["email"]),
        (_participant_name(friend), friend["email"]),
    ]
    description = (
        f"{_participant_name(sender)} invited you to watch {title.strip()}."
    )
    if message:
        description = f"{description}\n\n{message}"

    calendar_content = build_calendar_invitation(
        uid=invitation["uid"],
        summary=invitation["eventSummary"],
        starts_at=_parse_datetime(invitation["startsAt"]),
        ends_at=_parse_datetime(invitation["endsAt"]),
        organizer_email=sender_email,
        attendees=recipients,
        location=invitation["location"],
        description=description,
        sequence=invitation["calendarSequence"],
    )
    email_message = build_invitation_email(
        sender_name="Moview",
        sender_email=sender_email,
        recipients=recipients,
        subject=f"Movie night: {title.strip()}",
        calendar_content=calendar_content,
    )

    try:
        provider_message_id = send_invitation_email(
            message=email_message,
            sender_email=sender_email,
            recipient_emails=[address for _, address in recipients],
        )
    except Exception as error:
        with suppress(Exception):
            mark_movie_invitation_failed(
                invitation_id=invitation["id"],
                error_message=str(error),
            )
        raise

    updated = mark_movie_invitation_sent(
        invitation_id=invitation["id"],
        provider_message_id=provider_message_id,
    )
    return _public_invitation(updated)


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("Invitation start time is required.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError("Invitation start time is invalid.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError("Invitation start time must include a UTC offset.")
    return parsed


def _timezone_name(value: Any) -> str:
    name = _required_text(value, "Time zone", 255)
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise RuntimeError("Time zone is invalid.") from error
    return name


def _duration(value: Any) -> int:
    duration = _positive_integer(value, "Duration")
    if not MINIMUM_DURATION_MINUTES <= duration <= MAXIMUM_DURATION_MINUTES:
        raise RuntimeError("Duration must be between 15 and 480 minutes.")
    return duration


def _positive_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RuntimeError(f"{label} is required.")
    return value


def _required_text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{label} is required.")
    value = value.strip()
    if len(value) > maximum:
        raise RuntimeError(f"{label} is too long.")
    return value


def _optional_text(
    value: Any,
    label: str,
    maximum: int,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"{label} must be text.")
    value = value.strip()
    if len(value) > maximum:
        raise RuntimeError(f"{label} is too long.")
    return value or None


def _participant_name(participant: dict[str, Any]) -> str:
    name = " ".join(
        value
        for value in (
            participant.get("firstName"),
            participant.get("lastName"),
        )
        if value
    )
    return name or participant["username"]


def _public_invitation(invitation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in invitation.items()
        if key not in {"sender", "friend", "idempotencyKey"}
    }
