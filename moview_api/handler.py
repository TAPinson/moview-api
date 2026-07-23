from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

from graphql import graphql_sync

from moview_api.db import create_user_profile
from moview_api.tmdb import discover_movies_by_genre, search_movies
from moview_api.schema import (
    build_accept_friend_request_response,
    build_add_like_response,
    build_cancel_friend_request_response,
    build_create_profile_photo_upload_response,
    build_decline_friend_request_response,
    build_friends_response,
    build_incoming_friend_requests_response,
    build_outgoing_friend_requests_response,
    build_remove_friend_response,
    build_send_friend_request_response,
    build_shared_watchlist_response,
    build_user_search_response,
    build_add_to_watchlist_response,
    build_likes_response,
    build_mark_watched_response,
    build_remove_like_response,
    build_remove_from_watchlist_response,
    build_update_user_response,
    build_user_profile_response,
    build_watchlist_entries_response,
    build_watchlist_response,
    schema,
)


JsonObject = dict[str, Any]


def lambda_handler(event: JsonObject, context: Any) -> JsonObject:
    """AWS Lambda entry point for HTTP GraphQL, AppSync, and Cognito events."""
    if _is_cognito_post_confirmation_event(event):
        return _handle_cognito_post_confirmation(event)

    if _is_appsync_resolver_event(event):
        return _handle_appsync_resolver(event, context)

    return _handle_http_graphql(event, context)


def _handle_http_graphql(event: JsonObject, context: Any) -> JsonObject:
    method = _http_method(event)
    if method == "GET":
        params = event.get("queryStringParameters") or {}
        query = params.get("query")
        variables = _json_or_none(params.get("variables"))
        operation_name = params.get("operationName")
    else:
        payload = _json_body(event)
        query = payload.get("query")
        variables = payload.get("variables")
        operation_name = payload.get("operationName")

    if not query:
        return _http_response(400, {"errors": [{"message": "Missing GraphQL query."}]})

    result = graphql_sync(
        schema,
        query,
        variable_values=variables,
        operation_name=operation_name,
        context_value={"event": event, "lambda_context": context},
    )

    body: JsonObject = {}
    if result.errors:
        body["errors"] = [_format_graphql_error(error) for error in result.errors]
    if result.data is not None:
        body["data"] = result.data

    return _http_response(200 if not result.errors else 400, body)


def _handle_appsync_resolver(event: JsonObject, context: Any) -> JsonObject:
    field_name = _appsync_field_name(event)
    arguments = event.get("arguments") or {}

    if field_name == "health":
        return {"ok": True, "service": "moview-api"}

    if field_name == "users":
        return {}

    if field_name == "movies":
        return {}

    if field_name == "search":
        return search_movies(arguments.get("query") or "")

    if field_name == "byGenre":
        return discover_movies_by_genre(
            arguments.get("genreId"), arguments.get("page", 1)
        )

    if field_name == "findUsers":
        return build_user_search_response(_appsync_claims(event), arguments.get("query") or "")

    if field_name == "friends":
        return build_friends_response(_appsync_claims(event))

    if field_name == "incomingFriendRequests":
        return build_incoming_friend_requests_response(_appsync_claims(event))

    if field_name == "outgoingFriendRequests":
        return build_outgoing_friend_requests_response(_appsync_claims(event))

    if field_name == "sendFriendRequest":
        return build_send_friend_request_response(_appsync_claims(event), arguments.get("userId"))

    if field_name == "acceptFriendRequest":
        return build_accept_friend_request_response(_appsync_claims(event), arguments.get("userId"))

    if field_name == "declineFriendRequest":
        return build_decline_friend_request_response(_appsync_claims(event), arguments.get("userId"))

    if field_name == "cancelFriendRequest":
        return build_cancel_friend_request_response(_appsync_claims(event), arguments.get("userId"))

    if field_name == "removeFriend":
        return build_remove_friend_response(_appsync_claims(event), arguments.get("userId"))

    if field_name == "profile":
        return build_user_profile_response(_appsync_claims(event))

    if field_name == "watchlist":
        return build_watchlist_response(_appsync_claims(event), arguments.get("status"))

    if field_name == "sharedWatchlist":
        return build_shared_watchlist_response(
            _appsync_claims(event),
            arguments.get("friendUserId"),
        )

    if field_name == "watchlistEntries":
        return build_watchlist_entries_response(_appsync_claims(event))

    if field_name == "likes":
        return build_likes_response(_appsync_claims(event))

    if field_name == "updateUser":
        return build_update_user_response(
            _appsync_claims(event), arguments.get("input") or {}
        )

    if field_name == "createProfilePhotoUpload":
        return build_create_profile_photo_upload_response(
            _appsync_claims(event), arguments.get("contentType")
        )

    if field_name == "addLike":
        return build_add_like_response(_appsync_claims(event), arguments.get("movieId"))

    if field_name == "removeLike":
        return build_remove_like_response(_appsync_claims(event), arguments.get("movieId"))

    if field_name == "addToWatchlist":
        return build_add_to_watchlist_response(
            _appsync_claims(event), arguments.get("movieId")
        )

    if field_name == "markWatched":
        return build_mark_watched_response(_appsync_claims(event), arguments.get("movieId"))

    if field_name == "removeFromWatchlist":
        return build_remove_from_watchlist_response(
            _appsync_claims(event), arguments.get("movieId")
        )

    raise ValueError(f"Unsupported AppSync field: {field_name}")


def _is_cognito_post_confirmation_event(event: JsonObject) -> bool:
    trigger_source = event.get("triggerSource")
    return isinstance(trigger_source, str) and trigger_source.startswith(
        "PostConfirmation_"
    )


def _handle_cognito_post_confirmation(event: JsonObject) -> JsonObject:
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


def _is_appsync_resolver_event(event: JsonObject) -> bool:
    return _appsync_field_name(event) is not None


def _appsync_field_name(event: JsonObject) -> str | None:
    info = event.get("info") or {}
    return event.get("fieldName") or info.get("fieldName")


def _appsync_claims(event: JsonObject) -> dict[str, Any]:
    identity = event.get("identity") or {}
    claims = identity.get("claims")
    return claims if isinstance(claims, dict) else {}


def _http_method(event: JsonObject) -> str:
    request_context = event.get("requestContext") or {}
    http_context = request_context.get("http") or {}
    return (
        http_context.get("method")
        or request_context.get("httpMethod")
        or event.get("httpMethod")
        or "POST"
    ).upper()


def _json_body(event: JsonObject) -> JsonObject:
    body = event.get("body")
    if body is None:
        return event if "query" in event else {}

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    if isinstance(body, dict):
        return body

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _json_or_none(value: str | None) -> Any:
    if not value:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _http_response(status_code: int, body: JsonObject) -> JsonObject:
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
        },
        "body": json.dumps(body),
    }


def _format_graphql_error(error: Any) -> JsonObject:
    formatted: JsonObject = {"message": error.message}
    if error.locations:
        formatted["locations"] = [
            {"line": location.line, "column": location.column}
            for location in error.locations
        ]
    if error.path:
        formatted["path"] = error.path
    return formatted


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m moview_api.handler <event.json>")

    event = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    response = lambda_handler(event, context=None)
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()

