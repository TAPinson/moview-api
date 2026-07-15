from __future__ import annotations

import json
import os
import ssl
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


DATABASE_URL_KEYS = ("DATABASE_URL", "database_url", "url")



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


def add_movie_like(
    *,
    user_uuid: str,
    email: str,
    movie_id: int,
) -> dict[str, Any]:
    username = f"user-{user_uuid}"
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                select id from users
                where email = %s or username = %s
                order by id
                limit 1
                """,
                (email, username),
            )
            user_row = cursor.fetchone()
            if user_row is None:
                raise RuntimeError("User profile was not found.")

            user_id = user_row[0]
            cursor.execute(
                """
                insert into movie_likes (user_id, movie_id)
                values (%s, %s)
                on conflict (user_id, movie_id) do nothing
                """,
                (user_id, movie_id),
            )
            cursor.execute(
                """
                select user_id, movie_id, created_at
                from movie_likes
                where user_id = %s and movie_id = %s
                """,
                (user_id, movie_id),
            )
            like_row = cursor.fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()

    if like_row is None:
        raise RuntimeError("Movie like was not created.")

    return _movie_like_from_row(like_row)


def _movie_like_from_row(row: Any) -> dict[str, Any]:
    created_at = row[2]
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

    return {
        "userId": row[0],
        "movieId": row[1],
        "createdAt": created_at,
    }


def get_watchlist(
    *,
    user_uuid: str,
    email: str,
    status: str | None = None,
) -> list[dict[str, Any]]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            if status:
                cursor.execute(
                    """
                    select user_id, movie_id, status, added_at, watched_at, notes
                    from movie_watchlist
                    where user_id = %s and status = %s
                    order by added_at desc
                    """,
                    (user_id, status),
                )
            else:
                cursor.execute(
                    """
                    select user_id, movie_id, status, added_at, watched_at, notes
                    from movie_watchlist
                    where user_id = %s
                    order by added_at desc
                    """,
                    (user_id,),
                )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    return [_watchlist_item_from_row(row) for row in rows]


def add_to_watchlist(
    *,
    user_uuid: str,
    email: str,
    movie_id: int,
) -> dict[str, Any]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    return _upsert_watchlist_item(user_id=user_id, movie_id=movie_id, status="want_to_watch")


def mark_movie_watched(
    *,
    user_uuid: str,
    email: str,
    movie_id: int,
) -> dict[str, Any]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    return _upsert_watchlist_item(user_id=user_id, movie_id=movie_id, status="watched")


def remove_from_watchlist(
    *,
    user_uuid: str,
    email: str,
    movie_id: int,
) -> bool:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                delete from movie_watchlist
                where user_id = %s and movie_id = %s
                """,
                (user_id, movie_id),
            )
            removed = cursor.rowcount > 0
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()

    return removed


def _upsert_watchlist_item(*, user_id: int, movie_id: int, status: str) -> dict[str, Any]:
    watched_at_sql = "now()" if status == "watched" else "null"
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"""
                insert into movie_watchlist (user_id, movie_id, status, watched_at)
                values (%s, %s, %s, {watched_at_sql})
                on conflict (user_id, movie_id) do update
                set status = excluded.status,
                    watched_at = excluded.watched_at
                returning user_id, movie_id, status, added_at, watched_at, notes
                """,
                (user_id, movie_id, status),
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
        raise RuntimeError("Watchlist item was not saved.")

    return _watchlist_item_from_row(row)


def _user_id_for_identity(*, user_uuid: str, email: str) -> int:
    username = f"user-{user_uuid}"
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                select id from users
                where email = %s or username = %s
                order by id
                limit 1
                """,
                (email, username),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()

    if row is None:
        raise RuntimeError("User profile was not found.")

    return row[0]


def _watchlist_item_from_row(row: Any) -> dict[str, Any]:
    added_at = row[3]
    watched_at = row[4]
    if hasattr(added_at, "isoformat"):
        added_at = added_at.isoformat()
    if hasattr(watched_at, "isoformat"):
        watched_at = watched_at.isoformat()

    return {
        "userId": row[0],
        "movieId": row[1],
        "status": row[2],
        "addedAt": added_at,
        "watchedAt": watched_at,
        "notes": row[5],
    }


def update_user_profile(
    *,
    user_uuid: str,
    email: str,
    username: str,
    first_name: str | None,
    last_name: str | None,
) -> dict[str, Any]:
    default_username = f"user-{user_uuid}"
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                update users
                set username = %s,
                    first_name = %s,
                    last_name = %s
                where email = %s or username = %s
                returning id, username, email, admin, first_name, last_name
                """,
                (username, first_name, last_name, email, default_username),
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
        raise RuntimeError("User profile was not found.")

    return _user_profile_from_row(row)


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
