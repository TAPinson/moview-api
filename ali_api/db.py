from __future__ import annotations

import json
import os
import ssl
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


DATABASE_URL_KEYS = ("DATABASE_URL", "database_url", "url")


def get_postgres_now() -> str:
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("select now()")
            row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()

    if row is None:
        raise RuntimeError("Postgres did not return a timestamp.")

    value = row[0]
    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def create_user_profile(
    *,
    user_uuid: str,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:
    get_or_create_user_profile(
        user_uuid=user_uuid,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )


def get_or_create_user_profile(
    *,
    user_uuid: str,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict[str, Any]:
    username = f"user-{user_uuid}"
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                insert into users (username, email, admin, first_name, last_name)
                select %s, %s, false, %s, %s
                where not exists (
                    select 1 from users where email = %s or username = %s
                )
                """,
                (username, email, first_name, last_name, email, username),
            )
            cursor.execute(
                """
                select id, username, email, admin, first_name, last_name
                from users
                where email = %s or username = %s
                order by id
                limit 1
                """,
                (email, username),
            )
            row = cursor.fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()

    if row is None:
        raise RuntimeError("User profile was not created.")

    return _user_profile_from_row(row)


def _user_profile_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "admin": row[3],
        "firstName": row[4],
        "lastName": row[5],
    }


def _connect(database_url: str) -> Any:
    import pg8000.dbapi

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL must be a postgres:// or postgresql:// URL.")

    database = parsed.path.lstrip("/")
    if not parsed.hostname or not parsed.username or not database:
        raise RuntimeError("DATABASE_URL must include host, username, and database name.")

    query = parse_qs(parsed.query)
    sslmode = query.get("sslmode", ["require"])[0]
    ssl_context = None if sslmode == "disable" else ssl.create_default_context()

    return pg8000.dbapi.connect(
        user=unquote(parsed.username),
        password=unquote(parsed.password or ""),
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=database,
        ssl_context=ssl_context,
    )


def _database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    secret_id = os.environ.get("DATABASE_URL_SECRET_ARN") or os.environ.get(
        "DATABASE_URL_SECRET_ID"
    )
    if not secret_id:
        raise RuntimeError(
            "Set DATABASE_URL or DATABASE_URL_SECRET_ARN to connect to Postgres."
        )

    return _database_url_from_secret(secret_id)


@lru_cache(maxsize=1)
def _database_url_from_secret(secret_id: str) -> str:
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    secret = response.get("SecretString")
    if not secret:
        raise RuntimeError("Database URL secret must be stored as SecretString.")

    return _parse_database_url_secret(secret)


def _parse_database_url_secret(secret: str) -> str:
    try:
        parsed: Any = json.loads(secret)
    except json.JSONDecodeError:
        return secret

    if isinstance(parsed, str):
        return parsed

    if isinstance(parsed, dict):
        for key in DATABASE_URL_KEYS:
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value

    raise RuntimeError(
        "Database URL secret must be plaintext or JSON with a DATABASE_URL field."
    )
