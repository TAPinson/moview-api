from __future__ import annotations

import os
from typing import Any


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
PROFILE_PHOTO_URL_TTL_SECONDS = 3600
PROFILE_PHOTO_UPLOAD_TTL_SECONDS = 300


def _s3_client() -> Any:
    import boto3

    return boto3.client("s3")


def profile_photo_key(user_id: int) -> str:
    if not isinstance(user_id, int) or user_id <= 0:
        raise RuntimeError("A valid user ID is required.")
    return f"user/{user_id}/profile"


def profile_photo_url(user_id: int) -> str | None:
    bucket = os.environ.get("PROFILE_PHOTO_BUCKET")
    if not bucket:
        return None

    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": profile_photo_key(user_id)},
        ExpiresIn=PROFILE_PHOTO_URL_TTL_SECONDS,
    )


def create_profile_photo_upload(
    user_id: int,
    content_type: str,
) -> dict[str, Any]:
    bucket = os.environ.get("PROFILE_PHOTO_BUCKET")
    if not bucket:
        raise RuntimeError("Profile photo storage is not configured.")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise RuntimeError("Profile photos must be JPEG, PNG, or WebP.")

    upload = _s3_client().generate_presigned_post(
        Bucket=bucket,
        Key=profile_photo_key(user_id),
        Fields={"Content-Type": content_type, "Cache-Control": "no-cache"},
        Conditions=[
            {"Content-Type": content_type},
            {"Cache-Control": "no-cache"},
            ["content-length-range", 1, MAX_PROFILE_PHOTO_BYTES],
        ],
        ExpiresIn=PROFILE_PHOTO_UPLOAD_TTL_SECONDS,
    )

    return {
        "url": upload["url"],
        "fields": [
            {"name": name, "value": value}
            for name, value in upload["fields"].items()
        ],
    }
