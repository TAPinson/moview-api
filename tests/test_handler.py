from __future__ import annotations

import json
from types import SimpleNamespace

from ali_api.handler import lambda_handler


def test_http_graphql_hello(monkeypatch) -> None:
    monkeypatch.setattr(
        "ali_api.schema.get_postgres_now", lambda: "2026-07-13 12:34:56+00"
    )

    event = {
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(
            {
                "query": "query Hello($name: String) { hello(name: $name) { message requestId } }",
                "variables": {"name": "Ali"},
            }
        ),
    }
    context = SimpleNamespace(aws_request_id="request-123")

    response = lambda_handler(event, context)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body == {
        "data": {
            "hello": {
                "message": "Hello, Ali! 2026-07-13 12:34:56+00",
                "requestId": "request-123",
            }
        }
    }


def test_http_graphql_health() -> None:
    event = {
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps({"query": "{ health { ok service } }"}),
    }

    response = lambda_handler(event, context=None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body == {"data": {"health": {"ok": True, "service": "moview-api"}}}


def test_appsync_hello_resolver(monkeypatch) -> None:
    monkeypatch.setattr(
        "ali_api.schema.get_postgres_now", lambda: "2026-07-13 12:34:56+00"
    )

    event = {
        "arguments": {"name": "Ali"},
        "info": {"fieldName": "hello", "parentTypeName": "Query"},
    }
    context = SimpleNamespace(aws_request_id="request-123")

    response = lambda_handler(event, context)

    assert response == {
        "message": "Hello, Ali! 2026-07-13 12:34:56+00",
        "requestId": "request-123",
    }


def test_appsync_health_resolver() -> None:
    event = {
        "arguments": {},
        "info": {"fieldName": "health", "parentTypeName": "Query"},
    }

    response = lambda_handler(event, context=None)

    assert response == {"ok": True, "service": "moview-api"}


def test_cognito_post_confirmation_creates_user_profile(monkeypatch) -> None:
    created = {}

    def fake_create_user_profile(**kwargs) -> None:
        created.update(kwargs)

    monkeypatch.setattr("ali_api.handler.create_user_profile", fake_create_user_profile)
    event = {
        "triggerSource": "PostConfirmation_ConfirmSignUp",
        "request": {
            "userAttributes": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "email": "ali@example.com",
                "given_name": "Ali",
                "family_name": "Example",
            }
        },
    }

    response = lambda_handler(event, context=None)

    assert response is event
    assert created == {
        "user_uuid": "123e4567-e89b-12d3-a456-426614174000",
        "email": "ali@example.com",
        "first_name": "Ali",
        "last_name": "Example",
    }


def test_appsync_me_resolver(monkeypatch) -> None:
    profile = {
        "id": 1,
        "username": "user-123e4567-e89b-12d3-a456-426614174000",
        "email": "ali@example.com",
        "admin": False,
        "firstName": "Ali",
        "lastName": "Example",
    }

    def fake_get_or_create_user_profile(**kwargs):
        assert kwargs == {
            "user_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "ali@example.com",
            "first_name": "Ali",
            "last_name": "Example",
        }
        return profile

    monkeypatch.setattr(
        "ali_api.schema.get_or_create_user_profile", fake_get_or_create_user_profile
    )
    event = {
        "arguments": {},
        "info": {"fieldName": "me", "parentTypeName": "Query"},
        "identity": {
            "claims": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "email": "ali@example.com",
                "given_name": "Ali",
                "family_name": "Example",
            }
        },
    }

    assert lambda_handler(event, context=None) == profile
