from __future__ import annotations

from typing import Any

from moview_api.db import create_user_profile


JsonObject = dict[str, Any]


def is_post_confirmation_event(event: JsonObject) -> bool:
    trigger_source = event.get("triggerSource")
    return isinstance(trigger_source, str) and trigger_source.startswith(
        "PostConfirmation_"
    )


def handle_post_confirmation(event: JsonObject) -> JsonObject:
    request = event.get("request") or {}
    attributes = request.get("userAttributes") or {}
    user_uuid = attributes.get("sub")
    email = attributes.get("email")

    if not user_uuid or not email:
        raise ValueError("Cognito post-confirmation event is missing sub or email.")

    create_user_profile(
        user_uuid=user_uuid,
        email=email,
        first_name=attributes.get("given_name"),
        last_name=attributes.get("family_name"),
    )
    return event
