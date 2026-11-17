from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from graphql import graphql_sync

from moview_api import comments, db
from moview_api.schema import schema


@pytest.fixture
def database(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = (7,)
    monkeypatch.setattr(db, "_database_url", lambda: "test-database")
    monkeypatch.setattr(db, "_connect", lambda _: connection)
    return cursor


@pytest.mark.parametrize("body", ["", " \n\t", "x" * 2001, "a\x00b", None])
def test_invalid_comment_body(body):
    with pytest.raises(RuntimeError):
        comments.comment_body(body)


def test_comment_body_trims_whitespace():
    assert comments.comment_body("  Good movie! \n") == "Good movie!"


@pytest.mark.parametrize("value", [0, -1, True, "1", None])
def test_invalid_ids(value):
    with pytest.raises(RuntimeError):
        comments.positive_id(value)


def test_delete_is_scoped_to_authenticated_author(database):
    database.rowcount = 0
    assert comments.delete_comment(
        user_uuid="subject", email="user@example.com", comment_id=99,
    ) is False
    sql, parameters = database.execute.call_args.args
    assert "where id = %s and user_id = %s" in sql
    assert parameters == (99, 7)


def test_pagination_uses_last_visible_comment(database):
    timestamp = datetime(2026, 11, 17, tzinfo=timezone.utc)
    database.fetchall.return_value = [
        (number, 550, "Comment", timestamp, 7, "alice", None, None)
        for number in range(21, 0, -1)
    ]
    result = comments.list_comments(
        user_uuid="subject", email="user@example.com", movie_id=550,
    )
    assert len(result["comments"]) == 20
    assert result["nextCursor"] == {
        "createdAt": timestamp.isoformat(),
        "id": 2,
    }
    assert all(item["canDelete"] for item in result["comments"])


def test_cursor_requires_timezone():
    with pytest.raises(RuntimeError, match="timezone"):
        comments.comment_cursor({"createdAt": "2026-11-17T12:00:00", "id": 1})


@pytest.mark.parametrize("query", [
    "{ movieComments(movieId: 550) { comments { id } } }",
    'mutation { addMovieComment(movieId: 550, body: "Hello") { id } }',
    "mutation { deleteMovieComment(commentId: 1) }",
])
def test_comments_require_authenticated_identity(query):
    result = graphql_sync(schema, query, context_value={})
    assert result.errors
    assert "Authenticated user identity" in result.errors[0].message
