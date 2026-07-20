from __future__ import annotations

from pathlib import Path
from typing import Any

from graphql import GraphQLResolveInfo, build_schema

from ali_api.db import (
    add_movie_like,
    get_movie_likes,
    remove_movie_like,
    add_to_watchlist,
    get_or_create_user_profile,
    get_watchlist,
    get_watchlist_entries,
    mark_movie_watched,
    remove_from_watchlist,
    update_user_profile,
)
from ali_api.tmdb import discover_movies_by_genre, get_movie_details, search_movies


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.graphql"


def resolve_health(_source: Any, _info: GraphQLResolveInfo) -> dict[str, Any]:
    return {"ok": True, "service": "moview-api"}


def resolve_users(_source: Any, _info: GraphQLResolveInfo) -> dict[str, Any]:
    return {}


def resolve_movies(_source: Any, _info: GraphQLResolveInfo) -> dict[str, Any]:
    return {}


def resolve_movie_search(
    _source: Any,
    _info: GraphQLResolveInfo,
    query: str,
) -> list[dict[str, Any]]:
    return search_movies(query)


def resolve_movies_by_genre(
    _source: Any, _info: GraphQLResolveInfo, genreId: int, page: int
) -> dict[str, Any]:
    return discover_movies_by_genre(genreId, page)


def resolve_profile(_source: Any, info: GraphQLResolveInfo) -> dict[str, Any]:
    claims = _identity_claims(info.context or {})
    return build_user_profile_response(claims)


def resolve_watchlist(
    _source: Any,
    info: GraphQLResolveInfo,
    status: str | None = None,
) -> list[dict[str, Any]]:
    claims = _identity_claims(info.context or {})
    return build_watchlist_response(claims, status)


def resolve_watchlist_entries(
    _source: Any,
    info: GraphQLResolveInfo,
) -> list[dict[str, Any]]:
    claims = _identity_claims(info.context or {})
    return build_watchlist_entries_response(claims)


def resolve_likes(
    _source: Any,
    info: GraphQLResolveInfo,
) -> list[dict[str, Any]]:
    claims = _identity_claims(info.context or {})
    return build_likes_response(claims)


def resolve_update_user(
    _source: Any,
    info: GraphQLResolveInfo,
    input: dict[str, Any],
) -> dict[str, Any]:
    claims = _identity_claims(info.context or {})
    return build_update_user_response(claims, input)


def resolve_add_like(
    _source: Any,
    info: GraphQLResolveInfo,
    movieId: int,
) -> dict[str, Any]:
    claims = _identity_claims(info.context or {})
    return build_add_like_response(claims, movieId)


def resolve_remove_like(
    _source: Any,
    info: GraphQLResolveInfo,
    movieId: int,
) -> bool:
    claims = _identity_claims(info.context or {})
    return build_remove_like_response(claims, movieId)


def resolve_add_to_watchlist(
    _source: Any,
    info: GraphQLResolveInfo,
    movieId: int,
) -> dict[str, Any]:
    claims = _identity_claims(info.context or {})
    return build_add_to_watchlist_response(claims, movieId)


def resolve_mark_watched(
    _source: Any,
    info: GraphQLResolveInfo,
    movieId: int,
) -> dict[str, Any]:
    claims = _identity_claims(info.context or {})
    return build_mark_watched_response(claims, movieId)


def resolve_remove_from_watchlist(
    _source: Any,
    info: GraphQLResolveInfo,
    movieId: int,
) -> bool:
    claims = _identity_claims(info.context or {})
    return build_remove_from_watchlist_response(claims, movieId)


def build_user_profile_response(claims: dict[str, Any]) -> dict[str, Any]:
    user_uuid = claims.get("sub")
    email = claims.get("email")
    if not user_uuid or not email:
        raise RuntimeError("Authenticated user identity is missing sub or email.")

    return get_or_create_user_profile(
        user_uuid=str(user_uuid),
        email=str(email),
        first_name=_optional_claim(claims, "given_name"),
        last_name=_optional_claim(claims, "family_name"),
    )


def build_add_like_response(claims: dict[str, Any], movie_id: int) -> dict[str, Any]:
    user_uuid, email = _required_identity(claims)
    movie_id = _required_movie_id(movie_id)

    return add_movie_like(
        user_uuid=user_uuid,
        email=email,
        movie_id=movie_id,
    )


def build_remove_like_response(claims: dict[str, Any], movie_id: int) -> bool:
    user_uuid, email = _required_identity(claims)
    movie_id = _required_movie_id(movie_id)

    return remove_movie_like(
        user_uuid=user_uuid,
        email=email,
        movie_id=movie_id,
    )


def build_watchlist_response(
    claims: dict[str, Any],
    status: str | None,
) -> list[dict[str, Any]]:
    user_uuid, email = _required_identity(claims)
    items = get_watchlist(user_uuid=user_uuid, email=email, status=status)
    return [_with_movie_details(item) for item in items]


def build_watchlist_entries_response(claims: dict[str, Any]) -> list[dict[str, Any]]:
    user_uuid, email = _required_identity(claims)
    return get_watchlist_entries(user_uuid=user_uuid, email=email)


def build_likes_response(claims: dict[str, Any]) -> list[dict[str, Any]]:
    user_uuid, email = _required_identity(claims)
    likes = get_movie_likes(user_uuid=user_uuid, email=email)
    return [_with_movie_details(like) for like in likes]


def _with_movie_details(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "movie": get_movie_details(item["movieId"])}


def build_add_to_watchlist_response(
    claims: dict[str, Any],
    movie_id: int,
) -> dict[str, Any]:
    user_uuid, email = _required_identity(claims)
    movie_id = _required_movie_id(movie_id)
    return add_to_watchlist(user_uuid=user_uuid, email=email, movie_id=movie_id)


def build_mark_watched_response(
    claims: dict[str, Any],
    movie_id: int,
) -> dict[str, Any]:
    user_uuid, email = _required_identity(claims)
    movie_id = _required_movie_id(movie_id)
    return mark_movie_watched(user_uuid=user_uuid, email=email, movie_id=movie_id)


def build_remove_from_watchlist_response(
    claims: dict[str, Any],
    movie_id: int,
) -> bool:
    user_uuid, email = _required_identity(claims)
    movie_id = _required_movie_id(movie_id)
    return remove_from_watchlist(user_uuid=user_uuid, email=email, movie_id=movie_id)


def _required_identity(claims: dict[str, Any]) -> tuple[str, str]:
    user_uuid = claims.get("sub")
    email = claims.get("email")
    if not user_uuid or not email:
        raise RuntimeError("Authenticated user identity is missing sub or email.")
    return str(user_uuid), str(email)


def _required_movie_id(movie_id: int) -> int:
    if not isinstance(movie_id, int):
        raise RuntimeError("Movie ID is required.")
    return movie_id


def build_update_user_response(
    claims: dict[str, Any],
    input: dict[str, Any],
) -> dict[str, Any]:
    user_uuid = claims.get("sub")
    email = claims.get("email")
    username = input.get("username")
    if not user_uuid or not email:
        raise RuntimeError("Authenticated user identity is missing sub or email.")
    if not isinstance(username, str) or not username.strip():
        raise RuntimeError("Username is required.")

    return update_user_profile(
        user_uuid=str(user_uuid),
        email=str(email),
        username=username.strip(),
        first_name=_optional_input(input, "firstName"),
        last_name=_optional_input(input, "lastName"),
    )


def _optional_input(input: dict[str, Any], key: str) -> str | None:
    value = input.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _identity_claims(context: dict[str, Any]) -> dict[str, Any]:
    event = context.get("event") or {}
    identity = event.get("identity") or {}
    claims = identity.get("claims")
    if isinstance(claims, dict):
        return claims

    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}
    claims = authorizer.get("claims")
    return claims if isinstance(claims, dict) else {}


def _optional_claim(claims: dict[str, Any], key: str) -> str | None:
    value = claims.get(key)
    return str(value) if value else None


schema = build_schema(SCHEMA_PATH.read_text(encoding="utf-8"))
query_type = schema.get_type("Query")
users_type = schema.get_type("Users")
movies_type = schema.get_type("Movies")
mutation_type = schema.get_type("Mutation")

if query_type is None:
    raise RuntimeError("Schema is missing Query type.")
if users_type is None:
    raise RuntimeError("Schema is missing Users type.")
if movies_type is None:
    raise RuntimeError("Schema is missing Movies type.")
if mutation_type is None:
    raise RuntimeError("Schema is missing Mutation type.")

query_type.fields["health"].resolve = resolve_health
query_type.fields["users"].resolve = resolve_users
query_type.fields["movies"].resolve = resolve_movies
users_type.fields["profile"].resolve = resolve_profile
users_type.fields["watchlist"].resolve = resolve_watchlist
users_type.fields["watchlistEntries"].resolve = resolve_watchlist_entries
users_type.fields["likes"].resolve = resolve_likes
movies_type.fields["search"].resolve = resolve_movie_search
movies_type.fields["byGenre"].resolve = resolve_movies_by_genre
mutation_type.fields["updateUser"].resolve = resolve_update_user
mutation_type.fields["addLike"].resolve = resolve_add_like
mutation_type.fields["removeLike"].resolve = resolve_remove_like
mutation_type.fields["addToWatchlist"].resolve = resolve_add_to_watchlist
mutation_type.fields["markWatched"].resolve = resolve_mark_watched
mutation_type.fields["removeFromWatchlist"].resolve = resolve_remove_from_watchlist

