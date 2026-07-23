from __future__ import annotations

import pytest

from moview_api import profile_photos


class FakeS3Client:
    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        assert operation == "get_object"
        assert Params == {"Bucket": "photos", "Key": "user/42/profile"}
        assert ExpiresIn == 3600
        return "https://example.test/photo"

    def generate_presigned_post(
        self, *, Bucket, Key, Fields, Conditions, ExpiresIn
    ):
        assert Bucket == "photos"
        assert Key == "user/42/profile"
        assert Fields["Content-Type"] == "image/jpeg"
        assert ["content-length-range", 1, 5 * 1024 * 1024] in Conditions
        assert ExpiresIn == 300
        return {
            "url": "https://example.test/upload",
            "fields": {"key": Key, **Fields},
        }


def test_profile_photo_url(monkeypatch) -> None:
    monkeypatch.setenv("PROFILE_PHOTO_BUCKET", "photos")
    monkeypatch.setattr(profile_photos, "_s3_client", FakeS3Client)

    assert profile_photos.profile_photo_url(42) == "https://example.test/photo"


def test_create_profile_photo_upload(monkeypatch) -> None:
    monkeypatch.setenv("PROFILE_PHOTO_BUCKET", "photos")
    monkeypatch.setattr(profile_photos, "_s3_client", FakeS3Client)

    upload = profile_photos.create_profile_photo_upload(42, "image/jpeg")

    assert upload["url"] == "https://example.test/upload"
    assert {"name": "key", "value": "user/42/profile"} in upload["fields"]


def test_create_profile_photo_upload_rejects_unsupported_content_type(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROFILE_PHOTO_BUCKET", "photos")

    with pytest.raises(RuntimeError, match="JPEG, PNG, or WebP"):
        profile_photos.create_profile_photo_upload(42, "image/svg+xml")
