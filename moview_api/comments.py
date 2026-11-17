from __future__ import annotations

from datetime import datetime
from typing import Any

from moview_api.db import _lookup_user_id, _transaction

PAGE_SIZE = 20


def positive_id(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise RuntimeError("A positive ID is required.")
    return value


def comment_body(value: Any) -> str:
    if not isinstance(value, str):
        raise RuntimeError("Comment text is required.")
    if len(value) > 2000:
        raise RuntimeError("Comments must be 2,000 characters or fewer.")
    value = value.strip()
    if not value:
        raise RuntimeError("Comment text is required.")
    if "\x00" in value:
        raise RuntimeError("Comment text contains an unsupported character.")
    return value


def comment_cursor(value: Any) -> tuple[datetime | None, int | None]:
    if value is None:
        return None, None
    try:
        timestamp = datetime.fromisoformat(value["createdAt"])
        cursor_id = positive_id(value["id"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("Invalid comments cursor.") from None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise RuntimeError("Comments cursor must include a timezone.")
    return timestamp, cursor_id


def _comment(row: Any, viewer_id: int) -> dict[str, Any]:
    return {
        "id": row[0],
        "movieId": row[1],
        "body": row[2],
        "createdAt": row[3].isoformat(),
        "author": {
            "id": row[4],
            "username": row[5],
            "firstName": row[6],
            "lastName": row[7],
        },
        "canDelete": row[4] == viewer_id,
    }


def list_comments(
    *,
    user_uuid: str,
    email: str,
    movie_id: int,
    before: Any = None,
) -> dict[str, Any]:
    movie_id = positive_id(movie_id)
    timestamp, cursor_id = comment_cursor(before)

    with _transaction() as cursor:
        viewer_id = _lookup_user_id(
            cursor, user_uuid=user_uuid, email=email,
        )
        cursor.execute(
            """
            select c.id, c.movie_id, c.body, c.created_at,
                   u.id, u.username, u.first_name, u.last_name
            from movie_comments c
            join users u on u.id = c.user_id
            where c.movie_id = %s
              and (
                %s::timestamptz is null
                or (c.created_at, c.id) < (%s::timestamptz, %s)
              )
            order by c.created_at desc, c.id desc
            limit %s
            """,
            (movie_id, timestamp, timestamp, cursor_id, PAGE_SIZE + 1),
        )
        rows = cursor.fetchall()

    comments = [_comment(row, viewer_id) for row in rows[:PAGE_SIZE]]
    next_cursor = None
    if len(rows) > PAGE_SIZE:
        last = comments[-1]
        next_cursor = {"createdAt": last["createdAt"], "id": last["id"]}
    return {"comments": comments, "nextCursor": next_cursor}


def add_comment(
    *,
    user_uuid: str,
    email: str,
    movie_id: int,
    body: str,
) -> dict[str, Any]:
    movie_id = positive_id(movie_id)
    body = comment_body(body)

    with _transaction() as cursor:
        user_id = _lookup_user_id(
            cursor, user_uuid=user_uuid, email=email,
        )
        cursor.execute(
            """
            with inserted as (
              insert into movie_comments (user_id, movie_id, body)
              values (%s, %s, %s)
              returning id, movie_id, body, created_at, user_id
            )
            select c.id, c.movie_id, c.body, c.created_at,
                   u.id, u.username, u.first_name, u.last_name
            from inserted c
            join users u on u.id = c.user_id
            """,
            (user_id, movie_id, body),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Comment was not created.")
        return _comment(row, user_id)


def delete_comment(
    *,
    user_uuid: str,
    email: str,
    comment_id: int,
) -> bool:
    comment_id = positive_id(comment_id)

    with _transaction() as cursor:
        user_id = _lookup_user_id(
            cursor, user_uuid=user_uuid, email=email,
        )
        cursor.execute(
            """
            delete from movie_comments
            where id = %s and user_id = %s
            """,
            (comment_id, user_id),
        )
        return cursor.rowcount > 0
