from __future__ import annotations

from pathlib import Path
from typing import Any

from graphql import GraphQLResolveInfo, build_schema

from ali_api.db import get_or_create_user_profile, get_postgres_now, update_user_profile


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.graphql"


def resolve_health(_source: Any, _info: GraphQLResolveInfo) -> dict[str, Any]:
    return {"ok": True, "service": "moview-api"}


def resolve_hello(
    _source: Any,
    info: GraphQLResolveInfo,
    name: str | None = None,
) -> dict[str, Any]:
    context = info.context or {}
    lambda_context = context.get("lambda_context")
    return build_hello_response(name, getattr(lambda_context, "aws_request_id", None))


def build_hello_response(name: str | None, request_id: str | None) -> dict[str, Any]:
    postgres_now = get_postgres_now()
    return {
        "message": f"Hello, {name or 'world'}! {postgres_now}",
        "requestId": request_id,
    }


def resolve_me(_source: Any, info: GraphQLResolveInfo) -> dict[str, Any]:
    claims = _identity_claims(info.context or {})
    return build_user_profile_response(claims)


def resolve_update_user(
    _source: Any,
    info: GraphQLResolveInfo,
    input: dict[str, Any],
) -> dict[str, Any]:
    claims = _identity_claims(info.context or {})
    return build_update_user_response(claims, input)


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
mutation_type = schema.get_type("Mutation")

if query_type is None:
    raise RuntimeError("Schema is missing Query type.")
if mutation_type is None:
    raise RuntimeError("Schema is missing Mutation type.")

query_type.fields["health"].resolve = resolve_health
query_type.fields["hello"].resolve = resolve_hello
query_type.fields["me"].resolve = resolve_me
mutation_type.fields["updateUser"].resolve = resolve_update_user

