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


def remove_movie_like(
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
                delete from movie_likes
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


def get_movie_likes(
    *,
    user_uuid: str,
    email: str,
) -> list[dict[str, Any]]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                select user_id, movie_id, created_at
                from movie_likes
                where user_id = %s
                order by created_at desc
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    return [_movie_like_from_row(row) for row in rows]


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


def get_watchlist_entries(
    *,
    user_uuid: str,
    email: str,
) -> list[dict[str, Any]]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                select user_id, movie_id, status
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

    return [
        {"userId": row[0], "movieId": row[1], "status": row[2]}
        for row in rows
    ]


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


def search_users_for_friends(
    *, user_uuid: str, email: str, query: str
) -> list[dict[str, Any]]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    normalized_query = query.strip()
    if not normalized_query:
        return []

    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                select u.id, u.username, u.first_name, u.last_name
                from users u
                where u.id <> %s
                  and u.username ilike %s
                  and not exists (
                    select 1
                    from friendships f
                    where f.user_low_id = least(cast(%s as integer), u.id)
                      and f.user_high_id = greatest(cast(%s as integer), u.id)
                  )
                order by u.username
                limit 20
                """,
                (user_id, f"%{normalized_query}%", user_id, user_id),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    return [_public_user_from_row(row) for row in rows]


def get_friends(*, user_uuid: str, email: str) -> list[dict[str, Any]]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    return _get_relationships(user_id=user_id, status="accepted")


def get_incoming_friend_requests(
    *, user_uuid: str, email: str
) -> list[dict[str, Any]]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    return _get_relationships(
        user_id=user_id, status="pending", requested_by_current_user=False
    )


def get_outgoing_friend_requests(
    *, user_uuid: str, email: str
) -> list[dict[str, Any]]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    return _get_relationships(
        user_id=user_id, status="pending", requested_by_current_user=True
    )


def send_friend_request(
    *, user_uuid: str, email: str, target_user_id: int
) -> dict[str, Any]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    target_user_id = _required_target_user_id(target_user_id)
    if user_id == target_user_id:
        raise RuntimeError("You cannot send a friend request to yourself.")

    user_low_id = min(user_id, target_user_id)
    user_high_id = max(user_id, target_user_id)
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("select id from users where id = %s", (target_user_id,))
            if cursor.fetchone() is None:
                raise RuntimeError("User was not found.")
            cursor.execute(
                """
                insert into friendships (
                  user_low_id, user_high_id, requested_by_user_id, status
                )
                values (%s, %s, %s, 'pending')
                on conflict (user_low_id, user_high_id) do nothing
                returning created_at, updated_at
                """,
                (user_low_id, user_high_id, user_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("A friend request or friendship already exists.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()

    return _relationship_with_user(
        user_id=target_user_id,
        status="pending",
        created_at=row[0],
        updated_at=row[1],
    )


def accept_friend_request(
    *, user_uuid: str, email: str, requester_user_id: int
) -> dict[str, Any]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    requester_user_id = _required_target_user_id(requester_user_id)
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                update friendships
                set status = 'accepted', updated_at = now()
                where user_low_id = least(cast(%s as integer), cast(%s as integer))
                  and user_high_id = greatest(cast(%s as integer), cast(%s as integer))
                  and status = 'pending'
                  and requested_by_user_id = cast(%s as integer)
                  and requested_by_user_id <> cast(%s as integer)
                returning created_at, updated_at
                """,
                (
                    user_id,
                    requester_user_id,
                    user_id,
                    requester_user_id,
                    requester_user_id,
                    user_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Incoming friend request was not found.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()

    return _relationship_with_user(
        user_id=requester_user_id,
        status="accepted",
        created_at=row[0],
        updated_at=row[1],
    )


def decline_friend_request(
    *, user_uuid: str, email: str, requester_user_id: int
) -> bool:
    return _delete_relationship(
        user_uuid=user_uuid,
        email=email,
        target_user_id=requester_user_id,
        status="pending",
        requester_must_be_target=True,
    )


def cancel_friend_request(
    *, user_uuid: str, email: str, target_user_id: int
) -> bool:
    return _delete_relationship(
        user_uuid=user_uuid,
        email=email,
        target_user_id=target_user_id,
        status="pending",
        requester_must_be_current=True,
    )


def remove_friend(*, user_uuid: str, email: str, friend_user_id: int) -> bool:
    return _delete_relationship(
        user_uuid=user_uuid,
        email=email,
        target_user_id=friend_user_id,
        status="accepted",
    )


def get_shared_watchlist(
    *,
    user_uuid: str,
    email: str,
    friend_user_id: int,
) -> list[dict[str, Any]]:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    friend_user_id = _required_target_user_id(friend_user_id)
    user_low_id, user_high_id = _canonical_user_pair(user_id, friend_user_id)

    if user_id == friend_user_id:
        raise RuntimeError("Select one of your friends.")

    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                select 1
                from friendships
                where user_low_id = cast(%s as integer)
                  and user_high_id = cast(%s as integer)
                  and status = 'accepted'
                """,
                (user_low_id, user_high_id),
            )
            if cursor.fetchone() is None:
                raise RuntimeError("The selected user is not an accepted friend.")

            cursor.execute(
                """
                select mine.user_id,
                       mine.movie_id,
                       mine.status,
                       mine.added_at,
                       mine.watched_at,
                       mine.notes
                from movie_watchlist mine
                join movie_watchlist theirs
                  on theirs.movie_id = mine.movie_id
                 and theirs.user_id = cast(%s as integer)
                where mine.user_id = cast(%s as integer)
                  and mine.status = 'want_to_watch'
                  and theirs.status = 'want_to_watch'
                order by mine.added_at desc
                """,
                (friend_user_id, user_id),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    return [_watchlist_item_from_row(row) for row in rows]


def _canonical_user_pair(user_id: int, other_user_id: int) -> tuple[int, int]:
    return min(user_id, other_user_id), max(user_id, other_user_id)


def _get_relationships(
    *,
    user_id: int,
    status: str,
    requested_by_current_user: bool | None = None,
) -> list[dict[str, Any]]:
    requester_clause = ""
    if requested_by_current_user is True:
        requester_clause = "and f.requested_by_user_id = cast(%s as integer)"
    elif requested_by_current_user is False:
        requester_clause = "and f.requested_by_user_id <> cast(%s as integer)"

    params: list[Any] = [user_id, user_id, user_id, status]
    if requested_by_current_user is not None:
        params.append(user_id)

    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"""
                select u.id, u.username, u.first_name, u.last_name,
                       f.status, f.created_at, f.updated_at
                from friendships f
                join users u on u.id = case
                  when f.user_low_id = %s then f.user_high_id
                  else f.user_low_id
                end
                where (f.user_low_id = %s or f.user_high_id = %s)
                  and f.status = %s
                  {requester_clause}
                order by f.updated_at desc
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    return [_relationship_from_row(row) for row in rows]


def _delete_relationship(
    *,
    user_uuid: str,
    email: str,
    target_user_id: int,
    status: str,
    requester_must_be_current: bool = False,
    requester_must_be_target: bool = False,
) -> bool:
    user_id = _user_id_for_identity(user_uuid=user_uuid, email=email)
    target_user_id = _required_target_user_id(target_user_id)
    requester_clause = ""
    params: list[Any] = [user_id, target_user_id, user_id, target_user_id, status]
    if requester_must_be_current:
        requester_clause = "and requested_by_user_id = cast(%s as integer)"
        params.append(user_id)
    elif requester_must_be_target:
        requester_clause = "and requested_by_user_id = cast(%s as integer)"
        params.append(target_user_id)

    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"""
                delete from friendships
                where user_low_id = least(cast(%s as integer), cast(%s as integer))
                  and user_high_id = greatest(cast(%s as integer), cast(%s as integer))
                  and status = %s
                  {requester_clause}
                """,
                tuple(params),
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


def _relationship_with_user(
    *, user_id: int, status: str, created_at: Any, updated_at: Any
) -> dict[str, Any]:
    connection = _connect(_database_url())
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "select id, username, first_name, last_name from users where id = %s",
                (user_id,),
            )
            user_row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()
    if user_row is None:
        raise RuntimeError("User was not found.")
    return {
        "user": _public_user_from_row(user_row),
        "status": status,
        "createdAt": _isoformat(created_at),
        "updatedAt": _isoformat(updated_at),
    }


def _relationship_from_row(row: Any) -> dict[str, Any]:
    return {
        "user": _public_user_from_row(row),
        "status": row[4],
        "createdAt": _isoformat(row[5]),
        "updatedAt": _isoformat(row[6]),
    }


def _public_user_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "username": row[1],
        "firstName": row[2],
        "lastName": row[3],
    }


def _required_target_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or user_id <= 0:
        raise RuntimeError("User ID is required.")
    return user_id


def _isoformat(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
