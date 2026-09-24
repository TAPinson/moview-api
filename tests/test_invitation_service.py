from __future__ import annotations

from datetime import datetime, timezone

import pytest

from moview_api import invitation_service


NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def invitation_record(status: str = "pending"):
    return {
        "id": 12,
        "uid": "invitation-12@moview",
        "createdByUserId": 1,
        "friendUserId": 2,
        "movieId": 550,
        "startsAt": "2026-10-03T23:30:00+00:00",
        "endsAt": "2026-10-04T02:00:00+00:00",
        "timezone": "America/Kentucky/Louisville",
        "eventSummary": "Watch Fight Club",
        "location": "Ali's house",
        "message": "Bring snacks",
        "calendarSequence": 0,
        "status": status,
        "idempotencyKey": "request-123",
        "providerMessageId": None,
        "createdAt": "2026-09-22T12:00:00+00:00",
        "updatedAt": "2026-09-22T12:00:00+00:00",
        "sentAt": None,
        "cancelledAt": None,
        "sender": {
            "id": 1,
            "username": "ali",
            "email": "ali@example.com",
            "firstName": "Ali",
            "lastName": "Example",
        },
        "friend": {
            "id": 2,
            "username": "friend",
            "email": "friend@example.com",
            "firstName": "Friendly",
            "lastName": "User",
        },
    }


def request_input():
    return {
        "friendUserId": 2,
        "movieId": 550,
        "startsAt": "2026-10-03T23:30:00Z",
        "timezone": "America/Kentucky/Louisville",
        "durationMinutes": 150,
        "location": "Ali's house",
        "message": "Bring snacks",
        "idempotencyKey": "request-123",
    }


def test_schedule_movie_invitation(monkeypatch) -> None:
    monkeypatch.setenv(
        "MOVIEW_INVITATION_SENDER_EMAIL",
        "movie-night@moview.example",
    )
    monkeypatch.setattr(
        invitation_service,
        "get_movie_details",
        lambda movie_id: {"id": movie_id, "title": "Fight Club"},
    )
    monkeypatch.setattr(
        invitation_service,
        "create_movie_invitation",
        lambda **kwargs: invitation_record(),
    )
    sent = {}

    def fake_send(**kwargs):
        sent.update(kwargs)
        return "ses-message-123"

    monkeypatch.setattr(
        invitation_service,
        "send_invitation_email",
        fake_send,
    )
    monkeypatch.setattr(
        invitation_service,
        "mark_movie_invitation_sent",
        lambda **kwargs: {
            **invitation_record(),
            "status": "sent",
            "providerMessageId": kwargs["provider_message_id"],
        },
    )

    result = invitation_service.schedule_movie_invitation(
        user_uuid="user-uuid",
        email="ali@example.com",
        input=request_input(),
        now=NOW,
    )

    assert result["status"] == "sent"
    assert result["providerMessageId"] == "ses-message-123"
    assert "sender" not in result
    assert "friend" not in result
    assert sent["recipient_emails"] == [
        "ali@example.com",
        "friend@example.com",
    ]


def test_schedule_movie_invitation_records_failure(monkeypatch) -> None:
    monkeypatch.setenv(
        "MOVIEW_INVITATION_SENDER_EMAIL",
        "movie-night@moview.example",
    )
    monkeypatch.setattr(
        invitation_service,
        "get_movie_details",
        lambda _movie_id: {"title": "Fight Club"},
    )
    monkeypatch.setattr(
        invitation_service,
        "create_movie_invitation",
        lambda **_kwargs: invitation_record(),
    )
    monkeypatch.setattr(
        invitation_service,
        "send_invitation_email",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("SES unavailable")
        ),
    )
    failure = {}
    monkeypatch.setattr(
        invitation_service,
        "mark_movie_invitation_failed",
        lambda **kwargs: failure.update(kwargs),
    )

    with pytest.raises(RuntimeError, match="SES unavailable"):
        invitation_service.schedule_movie_invitation(
            user_uuid="user-uuid",
            email="ali@example.com",
            input=request_input(),
            now=NOW,
        )

    assert failure == {
        "invitation_id": 12,
        "error_message": "SES unavailable",
    }


def test_schedule_movie_invitation_rejects_past_time() -> None:
    input = request_input()
    input["startsAt"] = "2026-09-21T12:00:00Z"

    with pytest.raises(RuntimeError, match="must be in the future"):
        invitation_service.schedule_movie_invitation(
            user_uuid="user-uuid",
            email="ali@example.com",
            input=input,
            now=NOW,
        )


def test_schedule_movie_invitation_rejects_invalid_timezone() -> None:
    input = request_input()
    input["timezone"] = "Somewhere/Imaginary"

    with pytest.raises(RuntimeError, match="Time zone is invalid"):
        invitation_service.schedule_movie_invitation(
            user_uuid="user-uuid",
            email="ali@example.com",
            input=input,
            now=NOW,
        )
