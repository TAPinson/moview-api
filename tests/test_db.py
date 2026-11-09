from unittest.mock import MagicMock

import pytest

from moview_api import db


@pytest.fixture
def database(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = (7,)
    cursor.rowcount = 1
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(db, "_database_url", lambda: "test-database")
    monkeypatch.setattr(db, "_connect", connect)
    return connect, connection, cursor


@pytest.mark.parametrize("status", [None, "want_to_watch", "watched"])
def test_watchlist_uses_one_connection(database, status):
    connect, connection, cursor = database
    cursor.fetchall.return_value = [
        (7, 550, "watched", "added", "watched", None),
    ]

    items = db.get_watchlist(
        user_uuid="subject", email="user@example.com", status=status,
    )

    connect.assert_called_once_with("test-database")
    connection.cursor.assert_called_once()
    assert cursor.execute.call_args_list[0].args[1] == (
        "user@example.com", "user-subject",
    )
    expected = (7, status) if status else (7,)
    assert cursor.execute.call_args_list[1].args[1] == expected
    assert items[0]["movieId"] == 550
    assert items[0]["userId"] == 7
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("rowcount", [0, 1])
def test_removal_uses_one_connection(database, rowcount):
    connect, connection, cursor = database
    cursor.rowcount = rowcount

    removed = db.remove_from_watchlist(
        user_uuid="subject", email="user@example.com", movie_id=550,
    )

    assert removed is (rowcount > 0)
    connect.assert_called_once()
    assert cursor.execute.call_args_list[1].args[1] == (7, 550)
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_missing_user_prevents_delete(database):
    _, connection, cursor = database
    cursor.fetchone.return_value = None

    with pytest.raises(RuntimeError, match="User profile was not found"):
        db.remove_from_watchlist(
            user_uuid="subject", email="user@example.com", movie_id=550,
        )

    assert cursor.execute.call_count == 1
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("failure_point", ["query", "commit", "cursor"])
def test_transaction_failure_rolls_back_and_closes(database, failure_point):
    _, connection, cursor = database
    failure = RuntimeError("database failure")
    if failure_point == "query":
        cursor.execute.side_effect = [None, failure]
    elif failure_point == "commit":
        connection.commit.side_effect = failure
    else:
        connection.cursor.side_effect = failure

    with pytest.raises(RuntimeError, match="database failure"):
        db.remove_from_watchlist(
            user_uuid="subject", email="user@example.com", movie_id=550,
        )

    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
    if failure_point != "cursor":
        cursor.close.assert_called_once()



def test_watchlist_entries_use_one_connection(database):
    connect, connection, cursor = database
    cursor.fetchall.return_value = [(7, 550, "want_to_watch")]

    entries = db.get_watchlist_entries(
        user_uuid="subject", email="user@example.com",
    )

    assert entries == [
        {"userId": 7, "movieId": 550, "status": "want_to_watch"},
    ]
    connect.assert_called_once()
    connection.cursor.assert_called_once()
    assert cursor.execute.call_args_list[1].args[1] == (7,)
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "operation,status",
    [
        (db.add_to_watchlist, "want_to_watch"),
        (db.mark_movie_watched, "watched"),
    ],
)
def test_watchlist_save_uses_one_connection(database, operation, status):
    connect, connection, cursor = database
    watched_at = "watched" if status == "watched" else None
    cursor.fetchone.side_effect = [
        (7,),
        (7, 550, status, "added", watched_at, "notes"),
    ]

    result = operation(
        user_uuid="subject", email="user@example.com", movie_id=550,
    )

    assert result == {
        "userId": 7,
        "movieId": 550,
        "status": status,
        "addedAt": "added",
        "watchedAt": watched_at,
        "notes": "notes",
    }
    connect.assert_called_once()
    connection.cursor.assert_called_once()
    sql, parameters = cursor.execute.call_args_list[1].args
    assert parameters == (7, 550, status)
    expected_timestamp = "now()" if status == "watched" else "null"
    assert f"values (%s, %s, %s, {expected_timestamp})" in sql
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "operation", [db.add_to_watchlist, db.mark_movie_watched],
)
@pytest.mark.parametrize("failure", ["query", "missing_row", "invalid_row"])
def test_watchlist_save_failure_rolls_back(database, operation, failure):
    _, connection, cursor = database
    if failure == "query":
        cursor.execute.side_effect = [None, RuntimeError("query failed")]
        expected_error = RuntimeError
    else:
        saved_row = None if failure == "missing_row" else (7, 550)
        cursor.fetchone.side_effect = [(7,), saved_row]
        expected_error = RuntimeError if saved_row is None else IndexError

    with pytest.raises(expected_error):
        operation(
            user_uuid="subject", email="user@example.com", movie_id=550,
        )

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_get_likes_uses_one_connection(database):
    connect, connection, cursor = database
    cursor.fetchall.return_value = [(7, 550, "created")]

    assert db.get_movie_likes(
        user_uuid="subject", email="user@example.com",
    ) == [{"userId": 7, "movieId": 550, "createdAt": "created"}]

    connect.assert_called_once()
    assert cursor.execute.call_args_list[1].args[1] == (7,)
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_add_like_uses_one_connection(database):
    connect, connection, cursor = database
    cursor.fetchone.side_effect = [(7,), (7, 550, "created")]

    assert db.add_movie_like(
        user_uuid="subject", email="user@example.com", movie_id=550,
    ) == {"userId": 7, "movieId": 550, "createdAt": "created"}

    connect.assert_called_once()
    assert cursor.execute.call_args_list[1].args[1] == (7, 550)
    assert cursor.execute.call_args_list[2].args[1] == (7, 550)
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("rowcount", [0, 1])
def test_remove_like_uses_one_connection(database, rowcount):
    connect, connection, cursor = database
    cursor.rowcount = rowcount

    assert db.remove_movie_like(
        user_uuid="subject", email="user@example.com", movie_id=550,
    ) is (rowcount > 0)

    connect.assert_called_once()
    assert cursor.execute.call_args_list[1].args[1] == (7, 550)
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("failure", ["query", "missing_row", "invalid_row"])
def test_add_like_failure_rolls_back(database, failure):
    _, connection, cursor = database
    if failure == "query":
        cursor.execute.side_effect = [None, RuntimeError("query failed")]
        expected_error = RuntimeError
    else:
        saved_row = None if failure == "missing_row" else (7, 550)
        cursor.fetchone.side_effect = [(7,), saved_row]
        expected_error = RuntimeError if saved_row is None else IndexError

    with pytest.raises(expected_error):
        db.add_movie_like(
            user_uuid="subject", email="user@example.com", movie_id=550,
        )

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.fixture(params=["send", "accept"])
def friendship_operation(request):
    timestamps = ("created", "updated")
    participant = (8, "friend", "First", "Last")
    if request.param == "send":
        return (
            db.send_friend_request,
            {"target_user_id": 8},
            [(7,), (8,), timestamps, participant],
            "pending",
            (7, 8, 7),
        )
    return (
        db.accept_friend_request,
        {"requester_user_id": 8},
        [(7,), timestamps, participant],
        "accepted",
        (7, 8, 7, 8, 8, 7),
    )


def test_friendship_mutation_uses_one_connection(database, friendship_operation):
    connect, connection, cursor = database
    operation, arguments, rows, status, write_parameters = friendship_operation
    cursor.fetchone.side_effect = rows

    result = operation(
        user_uuid="subject", email="user@example.com", **arguments,
    )

    assert result == {
        "user": {
            "id": 8,
            "username": "friend",
            "firstName": "First",
            "lastName": "Last",
        },
        "status": status,
        "createdAt": "created",
        "updatedAt": "updated",
    }
    connect.assert_called_once()
    connection.cursor.assert_called_once()
    assert cursor.execute.call_args_list[-2].args[1] == write_parameters
    assert cursor.execute.call_args_list[-1].args[1] == (8,)
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "failure",
    ["response_query", "missing_identity", "missing_transition",
     "missing_response", "invalid_response"],
)
def test_friendship_mutation_failure_rolls_back(
    database, friendship_operation, failure,
):
    _, connection, cursor = database
    operation, arguments, rows, _, _ = friendship_operation
    rows = list(rows)
    expected_error = RuntimeError

    if failure == "response_query":
        cursor.execute.side_effect = (
            [None] * (len(rows) - 1) + [RuntimeError("response query failed")]
        )
    elif failure == "missing_identity":
        rows[0] = None
    elif failure == "missing_transition":
        rows[-2] = None
    elif failure == "missing_response":
        rows[-1] = None
    else:
        rows[-1] = (8,)
        expected_error = IndexError
    cursor.fetchone.side_effect = rows

    with pytest.raises(expected_error):
        operation(
            user_uuid="subject", email="user@example.com", **arguments,
        )

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_send_friend_request_to_self_prevents_write(database):
    _, connection, cursor = database

    with pytest.raises(RuntimeError, match="to yourself"):
        db.send_friend_request(
            user_uuid="subject", email="user@example.com", target_user_id=7,
        )

    assert cursor.execute.call_count == 1
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "operation,status,guard,parameters",
    [
        (db.get_friends, "accepted", "", (7, 7, 7, "accepted")),
        (
            db.get_incoming_friend_requests,
            "pending",
            "and f.requested_by_user_id <> cast(%s as integer)",
            (7, 7, 7, "pending", 7),
        ),
        (
            db.get_outgoing_friend_requests,
            "pending",
            "and f.requested_by_user_id = cast(%s as integer)",
            (7, 7, 7, "pending", 7),
        ),
    ],
)
def test_relationship_reads_use_one_connection(
    database, operation, status, guard, parameters,
):
    connect, connection, cursor = database
    cursor.fetchall.return_value = [
        (8, "friend", "First", "Last", status, "created", "updated"),
    ]

    result = operation(user_uuid="subject", email="user@example.com")

    assert result == [{
        "user": {
            "id": 8, "username": "friend",
            "firstName": "First", "lastName": "Last",
        },
        "status": status,
        "createdAt": "created",
        "updatedAt": "updated",
    }]
    sql, actual_parameters = cursor.execute.call_args_list[1].args
    assert actual_parameters == parameters
    if guard:
        assert guard in sql
    else:
        assert "and f.requested_by_user_id" not in sql
    connect.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("query", [" friend ", "   "])
def test_friend_search_uses_one_connection(database, query):
    connect, connection, cursor = database
    cursor.fetchall.return_value = [(8, "friend", "First", "Last")]

    result = db.search_users_for_friends(
        user_uuid="subject", email="user@example.com", query=query,
    )

    if query.strip():
        assert result == [{
            "id": 8, "username": "friend",
            "firstName": "First", "lastName": "Last",
        }]
        assert cursor.execute.call_args_list[1].args[1] == (
            7, "%friend%", 7, 7,
        )
    else:
        assert result == []
        assert cursor.execute.call_count == 1
    connect.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "operation,arguments,parameters",
    [
        (
            db.decline_friend_request,
            {"requester_user_id": 8},
            (7, 8, 7, 8, "pending", 8),
        ),
        (
            db.cancel_friend_request,
            {"target_user_id": 8},
            (7, 8, 7, 8, "pending", 7),
        ),
        (
            db.remove_friend,
            {"friend_user_id": 8},
            (7, 8, 7, 8, "accepted"),
        ),
    ],
)
@pytest.mark.parametrize("rowcount", [0, 1])
def test_relationship_removal_uses_one_connection(
    database, operation, arguments, parameters, rowcount,
):
    connect, connection, cursor = database
    cursor.rowcount = rowcount

    result = operation(
        user_uuid="subject", email="user@example.com", **arguments,
    )

    assert result is (rowcount > 0)
    sql, actual_parameters = cursor.execute.call_args_list[1].args
    assert actual_parameters == parameters
    if len(parameters) == 6:
        assert "and requested_by_user_id = cast(%s as integer)" in sql
    else:
        assert "and requested_by_user_id" not in sql
    connect.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "operation,arguments",
    [
        (db.get_friends, {}),
        (db.get_incoming_friend_requests, {}),
        (db.get_outgoing_friend_requests, {}),
        (db.search_users_for_friends, {"query": "friend"}),
        (db.decline_friend_request, {"requester_user_id": 8}),
        (db.cancel_friend_request, {"target_user_id": 8}),
        (db.remove_friend, {"friend_user_id": 8}),
    ],
)
@pytest.mark.parametrize("failure", ["identity", "query"])
def test_relationship_operation_failure_rolls_back(
    database, operation, arguments, failure,
):
    _, connection, cursor = database
    if failure == "identity":
        cursor.fetchone.return_value = None
    else:
        cursor.execute.side_effect = [None, RuntimeError("query failed")]

    with pytest.raises(RuntimeError):
        operation(
            user_uuid="subject", email="user@example.com", **arguments,
        )

    if failure == "identity":
        assert cursor.execute.call_count == 1
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("friend_id", [3, 8])
@pytest.mark.parametrize("has_movies", [False, True])
def test_shared_watchlist_uses_one_connection(database, friend_id, has_movies):
    connect, connection, cursor = database
    cursor.fetchone.side_effect = [(7,), (1,)]
    cursor.fetchall.return_value = (
        [(7, 550, "want_to_watch", "added", None, "notes")]
        if has_movies else []
    )

    result = db.get_shared_watchlist(
        user_uuid="subject",
        email="user@example.com",
        friend_user_id=friend_id,
    )

    assert result == (
        [{
            "userId": 7,
            "movieId": 550,
            "status": "want_to_watch",
            "addedAt": "added",
            "watchedAt": None,
            "notes": "notes",
        }]
        if has_movies else []
    )
    assert cursor.execute.call_args_list[1].args[1] == (
        min(7, friend_id), max(7, friend_id),
    )
    assert cursor.execute.call_args_list[2].args[1] == (friend_id, 7)
    connect.assert_called_once()
    connection.cursor.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "failure,friend_id,identity,friendship,query_count",
    [
        ("missing_identity", 8, None, (1,), 1),
        ("self", 7, (7,), (1,), 1),
        ("invalid_friend", 0, (7,), (1,), 1),
        ("not_friends", 8, (7,), None, 2),
    ],
)
def test_shared_watchlist_rejects_before_movie_query(
    database, failure, friend_id, identity, friendship, query_count,
):
    _, connection, cursor = database
    cursor.fetchone.side_effect = [identity, friendship]

    with pytest.raises(RuntimeError):
        db.get_shared_watchlist(
            user_uuid="subject",
            email="user@example.com",
            friend_user_id=friend_id,
        )

    assert cursor.execute.call_count == query_count
    cursor.fetchall.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_shared_watchlist_query_failure_rolls_back(database):
    _, connection, cursor = database
    cursor.fetchone.side_effect = [(7,), (1,)]
    cursor.execute.side_effect = [None, None, RuntimeError("query failed")]

    with pytest.raises(RuntimeError, match="query failed"):
        db.get_shared_watchlist(
            user_uuid="subject",
            email="user@example.com",
            friend_user_id=8,
        )

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.fixture
def invitation_row():
    return (
        12, "invitation@moview", 7, 8, 550,
        "2027-01-01T18:00:00+00:00",
        "2027-01-01T20:00:00+00:00",
        "UTC", "Watch Movie", None, None, 0,
        "pending", "request-key", None,
        "created", "updated", None, None,
    )


@pytest.fixture
def invitation_arguments(invitation_row):
    return {
        "user_uuid": "subject",
        "email": "user@example.com",
        "friend_user_id": 8,
        "movie_id": 550,
        "uid": "invitation@moview",
        "starts_at": invitation_row[5],
        "ends_at": invitation_row[6],
        "timezone": "UTC",
        "event_summary": "Watch Movie",
        "location": None,
        "message": None,
        "idempotency_key": "request-key",
    }


@pytest.fixture
def invitation_database(database, invitation_row):
    connect, connection, cursor = database
    cursor.fetchone.side_effect = [(7,), (1,), (1,), invitation_row]
    cursor.fetchall.return_value = [
        (7, "sender", "user@example.com", "First", "Last"),
        (8, "friend", "friend@example.com", "Other", "Person"),
    ]
    return connect, connection, cursor


@pytest.mark.parametrize("status", ["pending", "sent"])
def test_create_invitation_uses_one_connection(
    invitation_database, invitation_row, invitation_arguments, status,
):
    connect, connection, cursor = invitation_database
    row = list(invitation_row)
    row[12] = status
    cursor.fetchone.side_effect = [(7,), (1,), (1,), tuple(row)]

    result = db.create_movie_invitation(**invitation_arguments)

    assert result["id"] == 12
    assert result["status"] == status
    assert result["sender"]["id"] == 7
    assert result["friend"]["id"] == 8
    assert cursor.execute.call_args_list[1].args[1] == (7, 8)
    assert cursor.execute.call_args_list[2].args[1] == (8, 7, 550)
    assert cursor.execute.call_args_list[3].args[1] == (
        "invitation@moview", 7, 8, 550,
        invitation_row[5], invitation_row[6],
        "UTC", "Watch Movie", None, None, "request-key",
    )
    assert cursor.execute.call_args_list[4].args[1] == (7, 8)
    connect.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "failure",
    [
        "identity", "self", "friendship", "watchlist", "insert",
        "conflict", "participant_query", "missing_participant",
        "invalid_participant", "invalid_row",
    ],
)
def test_create_invitation_failure_rolls_back(
    invitation_database, invitation_row, invitation_arguments, failure,
):
    _, connection, cursor = invitation_database
    rows = [(7,), (1,), (1,), invitation_row]
    arguments = dict(invitation_arguments)
    expected_error = RuntimeError

    if failure == "identity":
        rows[0] = None
    elif failure == "self":
        arguments["friend_user_id"] = 7
    elif failure == "friendship":
        rows[1] = None
    elif failure == "watchlist":
        rows[2] = None
    elif failure == "insert":
        rows[3] = None
    elif failure == "conflict":
        conflicting_row = list(invitation_row)
        conflicting_row[3] = 9
        rows[3] = tuple(conflicting_row)
    elif failure == "participant_query":
        cursor.execute.side_effect = (
            [None] * 4 + [RuntimeError("participant query failed")]
        )
    elif failure == "missing_participant":
        cursor.fetchall.return_value = [
            (7, "sender", "user@example.com", "First", "Last"),
        ]
    elif failure == "invalid_participant":
        cursor.fetchall.return_value = [(7,)]
        expected_error = IndexError
    else:
        rows[3] = (12,)
        expected_error = IndexError

    cursor.fetchone.side_effect = rows
    with pytest.raises(expected_error):
        db.create_movie_invitation(**arguments)

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("status", ["sent", "failed"])
def test_invitation_delivery_uses_transaction(database, invitation_row, status):
    connect, connection, cursor = database
    row = list(invitation_row)
    row[12] = status
    row[14] = "provider-id" if status == "sent" else None
    cursor.fetchone.return_value = tuple(row)

    if status == "sent":
        result = db.mark_movie_invitation_sent(
            invitation_id=12, provider_message_id="provider-id",
        )
        expected = ("sent", "provider-id", None, "sent", 12)
    else:
        result = db.mark_movie_invitation_failed(
            invitation_id=12, error_message="x" * 2001,
        )
        expected = ("failed", None, "x" * 2000, "failed", 12)

    assert result["status"] == status
    assert result["providerMessageId"] == row[14]
    sql, parameters = cursor.execute.call_args.args
    assert parameters == expected
    assert "and status <> 'cancelled'" in sql
    connect.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("failure", ["query", "missing_row", "invalid_row"])
def test_invitation_delivery_failure_rolls_back(database, failure):
    _, connection, cursor = database
    expected_error = RuntimeError
    if failure == "query":
        cursor.execute.side_effect = RuntimeError("query failed")
    elif failure == "missing_row":
        cursor.fetchone.return_value = None
    else:
        cursor.fetchone.return_value = (12,)
        expected_error = IndexError

    with pytest.raises(expected_error):
        db.mark_movie_invitation_sent(
            invitation_id=12, provider_message_id="provider-id",
        )

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.fixture(params=["get_or_create", "create", "update"])
def profile_operation(request):
    arguments = {
        "user_uuid": "subject",
        "email": "user@example.com",
        "first_name": "First",
        "last_name": "Last",
    }
    if request.param == "update":
        arguments["username"] = "custom"
        return (
            db.update_user_profile,
            arguments,
            [("custom", "First", "Last", "user@example.com", "user-subject")],
        )

    operation = (
        db.create_user_profile
        if request.param == "create"
        else db.get_or_create_user_profile
    )
    return (
        operation,
        arguments,
        [
            (
                "user-subject", "user@example.com", "First", "Last",
                "user@example.com", "user-subject",
            ),
            ("user@example.com", "user-subject"),
        ],
    )


def test_profile_operation_uses_one_connection(database, profile_operation):
    connect, connection, cursor = database
    operation, arguments, parameters = profile_operation
    cursor.fetchone.return_value = (
        7, "custom", "user@example.com", True, "First", "Last",
    )

    result = operation(**arguments)

    if operation is db.create_user_profile:
        assert result is None
    else:
        assert result == {
            "id": 7,
            "username": "custom",
            "email": "user@example.com",
            "admin": True,
            "firstName": "First",
            "lastName": "Last",
        }
    assert [
        call.args[1] for call in cursor.execute.call_args_list
    ] == parameters
    connect.assert_called_once()
    connection.cursor.assert_called_once()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("failure", ["query", "missing_row", "invalid_row"])
def test_profile_operation_failure_rolls_back(
    database, profile_operation, failure,
):
    _, connection, cursor = database
    operation, arguments, _ = profile_operation
    expected_error = RuntimeError
    if failure == "query":
        cursor.execute.side_effect = RuntimeError("query failed")
    elif failure == "missing_row":
        cursor.fetchone.return_value = None
    else:
        cursor.fetchone.return_value = (7,)
        expected_error = IndexError

    with pytest.raises(expected_error):
        operation(**arguments)

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
