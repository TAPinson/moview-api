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


def test_appsync_users_resolver() -> None:
    event = {
        "arguments": {},
        "info": {"fieldName": "users", "parentTypeName": "Query"},
    }

    assert lambda_handler(event, context=None) == {}


def test_appsync_users_profile_resolver(monkeypatch) -> None:
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
        "info": {"fieldName": "profile", "parentTypeName": "Users"},
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


def test_appsync_update_user_resolver(monkeypatch) -> None:
    profile = {
        "id": 1,
        "username": "ali",
        "email": "ali@example.com",
        "admin": False,
        "firstName": "Ali",
        "lastName": "Updated",
    }

    def fake_update_user_profile(**kwargs):
        assert kwargs == {
            "user_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "ali@example.com",
            "username": "ali",
            "first_name": "Ali",
            "last_name": "Updated",
        }
        return profile

    monkeypatch.setattr("ali_api.schema.update_user_profile", fake_update_user_profile)
    event = {
        "arguments": {
            "input": {
                "username": "ali",
                "firstName": "Ali",
                "lastName": "Updated",
            }
        },
        "info": {"fieldName": "updateUser", "parentTypeName": "Mutation"},
        "identity": {
            "claims": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "email": "ali@example.com",
            }
        },
    }

    assert lambda_handler(event, context=None) == profile


def test_appsync_movies_resolver() -> None:
    event = {
        "arguments": {},
        "info": {"fieldName": "movies", "parentTypeName": "Query"},
    }

    assert lambda_handler(event, context=None) == {}


def test_appsync_movie_search_resolver(monkeypatch) -> None:
    results = [
        {
            "poster_path": "/IfB9hy4JH1eH6HEfIgIGORXi5h.jpg",
            "adult": False,
            "overview": "Jack Reacher must uncover the truth behind a major government conspiracy in order to clear his name.",
            "release_date": "2016-10-19",
            "genre_ids": [53, 28, 80, 18, 9648],
            "id": 343611,
            "original_title": "Jack Reacher: Never Go Back",
            "original_language": "en",
            "title": "Jack Reacher: Never Go Back",
            "backdrop_path": "/4ynQYtSEuU5hyipcGkfD6ncwtwz.jpg",
            "popularity": 26.818468,
            "vote_count": 201,
            "video": False,
            "vote_average": 4.19,
        }
    ]

    def fake_search_movies(query: str):
        assert query == "Jack Reacher"
        return results

    monkeypatch.setattr("ali_api.handler.search_movies", fake_search_movies)
    event = {
        "arguments": {"query": "Jack Reacher"},
        "info": {"fieldName": "search", "parentTypeName": "Movies"},
    }

    assert lambda_handler(event, context=None) == results


def test_appsync_add_like_resolver(monkeypatch) -> None:
    like = {
        "userId": 1,
        "movieId": 343611,
        "createdAt": "2026-07-14T12:34:56+00:00",
    }

    def fake_add_movie_like(**kwargs):
        assert kwargs == {
            "user_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "ali@example.com",
            "movie_id": 343611,
        }
        return like

    monkeypatch.setattr("ali_api.schema.add_movie_like", fake_add_movie_like)
    event = {
        "arguments": {"movieId": 343611},
        "info": {"fieldName": "addLike", "parentTypeName": "Mutation"},
        "identity": {
            "claims": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "email": "ali@example.com",
            }
        },
    }

    assert lambda_handler(event, context=None) == like


def test_appsync_watchlist_resolver(monkeypatch) -> None:
    items = [
        {
            "userId": 1,
            "movieId": 343611,
            "status": "want_to_watch",
            "addedAt": "2026-07-14T12:00:00+00:00",
            "watchedAt": None,
            "notes": None,
        }
    ]

    def fake_get_watchlist(**kwargs):
        assert kwargs == {
            "user_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "ali@example.com",
            "status": "want_to_watch",
        }
        return items

    monkeypatch.setattr("ali_api.schema.get_watchlist", fake_get_watchlist)
    event = {
        "arguments": {"status": "want_to_watch"},
        "info": {"fieldName": "watchlist", "parentTypeName": "Users"},
        "identity": {
            "claims": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "email": "ali@example.com",
            }
        },
    }

    assert lambda_handler(event, context=None) == items


def test_appsync_add_to_watchlist_resolver(monkeypatch) -> None:
    item = {
        "userId": 1,
        "movieId": 343611,
        "status": "want_to_watch",
        "addedAt": "2026-07-14T12:00:00+00:00",
        "watchedAt": None,
        "notes": None,
    }

    def fake_add_to_watchlist(**kwargs):
        assert kwargs == {
            "user_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "ali@example.com",
            "movie_id": 343611,
        }
        return item

    monkeypatch.setattr("ali_api.schema.add_to_watchlist", fake_add_to_watchlist)
    event = {
        "arguments": {"movieId": 343611},
        "info": {"fieldName": "addToWatchlist", "parentTypeName": "Mutation"},
        "identity": {
            "claims": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "email": "ali@example.com",
            }
        },
    }

    assert lambda_handler(event, context=None) == item


def test_appsync_mark_watched_resolver(monkeypatch) -> None:
    item = {
        "userId": 1,
        "movieId": 343611,
        "status": "watched",
        "addedAt": "2026-07-14T12:00:00+00:00",
        "watchedAt": "2026-07-14T13:00:00+00:00",
        "notes": None,
    }

    def fake_mark_movie_watched(**kwargs):
        assert kwargs == {
            "user_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "ali@example.com",
            "movie_id": 343611,
        }
        return item

    monkeypatch.setattr("ali_api.schema.mark_movie_watched", fake_mark_movie_watched)
    event = {
        "arguments": {"movieId": 343611},
        "info": {"fieldName": "markWatched", "parentTypeName": "Mutation"},
        "identity": {
            "claims": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "email": "ali@example.com",
            }
        },
    }

    assert lambda_handler(event, context=None) == item


def test_appsync_remove_from_watchlist_resolver(monkeypatch) -> None:
    def fake_remove_from_watchlist(**kwargs):
        assert kwargs == {
            "user_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "ali@example.com",
            "movie_id": 343611,
        }
        return True

    monkeypatch.setattr(
        "ali_api.schema.remove_from_watchlist", fake_remove_from_watchlist
    )
    event = {
        "arguments": {"movieId": 343611},
        "info": {"fieldName": "removeFromWatchlist", "parentTypeName": "Mutation"},
        "identity": {
            "claims": {
                "sub": "123e4567-e89b-12d3-a456-426614174000",
                "email": "ali@example.com",
            }
        },
    }

    assert lambda_handler(event, context=None) is True
