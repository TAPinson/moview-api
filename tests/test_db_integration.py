import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pg8000.dbapi import DatabaseError

from moview_api import db


pytestmark = pytest.mark.skipif(
    os.environ.get("MOVIEW_RUN_POSTGRES_TESTS") != "1",
    reason="Set MOVIEW_RUN_POSTGRES_TESTS=1 to run Docker integration tests.",
)

SCHEMA_DIRECTORY = Path(__file__).resolve().parents[1] / "postgres"


@pytest.fixture(scope="session")
def postgres_url():
    name = f"moview-integration-{uuid4().hex}"
    password = uuid4().hex
    database = "moview_integration_test"

    try:
        subprocess.run(
            [
                "docker", "run", "--rm", "--detach",
                "--name", name,
                "--publish", "127.0.0.1::5432",
                "--tmpfs", "/var/lib/postgresql/data:rw,size=256m",
                "--env", f"POSTGRES_PASSWORD={password}",
                "--env", f"POSTGRES_DB={database}",
                "postgres:16-alpine",
            ],
            check=True, capture_output=True, text=True, timeout=120,
        )

        deadline = time.monotonic() + 30
        while True:
            ready = subprocess.run(
                [
                    "docker", "exec", name,
                    "pg_isready", "-h", "127.0.0.1",
                    "-U", "postgres", "-d", database,
                ],
                capture_output=True, timeout=5,
            )
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Integration Postgres did not become ready.")
            time.sleep(0.2)

        for filename in (
            "users.sql",
            "movie_watchlist.sql",
            "movie_likes.sql",
            "friendships.sql",
            "movie_invitations.sql",
        ):
            subprocess.run(
                [
                    "docker", "exec", "-i", name,
                    "psql", "-U", "postgres", "-d", database,
                    "-v", "ON_ERROR_STOP=1",
                ],
                input=(SCHEMA_DIRECTORY / filename).read_text(),
                check=True, capture_output=True, text=True, timeout=15,
            )

        port_result = subprocess.run(
            ["docker", "port", name, "5432/tcp"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        port = int(port_result.stdout.strip().rsplit(":", 1)[1])
        yield (
            f"postgresql://postgres:{password}@127.0.0.1:{port}/"
            f"{database}?sslmode=disable"
        )
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name],
            capture_output=True, timeout=15,
        )


@pytest.fixture
def accounts(postgres_url, monkeypatch):
    monkeypatch.setattr(db, "_database_url", lambda: postgres_url)

    with db._transaction() as cursor:
        cursor.execute("truncate users restart identity cascade")

    identities = [
        {"user_uuid": name, "email": f"{name}@example.com"}
        for name in ("alice", "bob", "carol")
    ]
    for identity in identities:
        db.create_user_profile(**identity)
    return identities


def rows(query, parameters=()):
    with db._transaction() as cursor:
        cursor.execute(query, parameters)
        return cursor.fetchall()


def test_profile_round_trip_and_constraint_rollback(accounts):
    alice, bob, _ = accounts
    original = db.get_or_create_user_profile(**alice)
    assert db.get_or_create_user_profile(**alice)["id"] == original["id"]
    assert rows("select count(*) from users")[0][0] == 3

    updated = db.update_user_profile(
        **alice, username="alice-custom",
        first_name="Alice", last_name="Example",
    )
    assert updated["id"] == original["id"]
    assert db.get_or_create_user_profile(**alice)["username"] == "alice-custom"

    bob_username = db.get_or_create_user_profile(**bob)["username"]
    with pytest.raises(DatabaseError) as error:
        db.update_user_profile(
            **alice, username=bob_username,
            first_name="Should roll back", last_name=None,
        )

    assert error.value.args[0]["C"] == "23505"

    profile = db.get_or_create_user_profile(**alice)
    assert profile["username"] == "alice-custom"
    assert profile["firstName"] == "Alice"


def test_watchlist_round_trip_and_ownership(accounts):
    alice, bob, _ = accounts
    first = db.add_to_watchlist(**alice, movie_id=550)
    assert db.add_to_watchlist(**alice, movie_id=550)["userId"] == first["userId"]
    db.add_to_watchlist(**alice, movie_id=551)
    db.add_to_watchlist(**bob, movie_id=551)

    watched = db.mark_movie_watched(**alice, movie_id=550)
    assert watched["status"] == "watched"
    assert watched["watchedAt"] is not None

    assert [
        item["movieId"]
        for item in db.get_watchlist(**alice, status="want_to_watch")
    ] == [551]
    assert [
        item["movieId"]
        for item in db.get_watchlist(**alice, status="watched")
    ] == [550]
    assert len(db.get_watchlist_entries(**alice)) == 2

    assert db.remove_from_watchlist(**alice, movie_id=551)
    assert not db.remove_from_watchlist(**alice, movie_id=551)
    assert [item["movieId"] for item in db.get_watchlist(**bob)] == [551]


def test_likes_round_trip_and_ownership(accounts):
    alice, bob, _ = accounts
    first = db.add_movie_like(**alice, movie_id=550)
    assert db.add_movie_like(**alice, movie_id=550) == first
    db.add_movie_like(**bob, movie_id=550)

    assert db.get_movie_likes(**alice) == [first]
    assert db.remove_movie_like(**alice, movie_id=550)
    assert not db.remove_movie_like(**alice, movie_id=550)
    assert db.get_movie_likes(**alice) == []
    assert len(db.get_movie_likes(**bob)) == 1


def test_friendship_transitions_and_direction_checks(accounts):
    alice, bob, _ = accounts
    alice_id = db.get_or_create_user_profile(**alice)["id"]
    bob_id = db.get_or_create_user_profile(**bob)["id"]

    db.send_friend_request(**alice, target_user_id=bob_id)
    assert len(db.get_outgoing_friend_requests(**alice)) == 1
    assert len(db.get_incoming_friend_requests(**bob)) == 1
    assert db.get_incoming_friend_requests(**alice) == []
    assert bob_id not in {
        user["id"]
        for user in db.search_users_for_friends(**alice, query="user-")
    }

    with pytest.raises(RuntimeError, match="Incoming friend request"):
        db.accept_friend_request(**alice, requester_user_id=bob_id)
    assert not db.cancel_friend_request(**bob, target_user_id=alice_id)
    assert not db.decline_friend_request(**alice, requester_user_id=bob_id)
    assert db.cancel_friend_request(**alice, target_user_id=bob_id)

    db.send_friend_request(**alice, target_user_id=bob_id)
    assert db.decline_friend_request(**bob, requester_user_id=alice_id)

    db.send_friend_request(**alice, target_user_id=bob_id)
    accepted = db.accept_friend_request(**bob, requester_user_id=alice_id)
    assert accepted["status"] == "accepted"
    assert db.get_friends(**alice)[0]["user"]["id"] == bob_id
    assert db.get_friends(**bob)[0]["user"]["id"] == alice_id
    assert db.get_outgoing_friend_requests(**alice) == []

    assert db.remove_friend(**alice, friend_user_id=bob_id)
    assert db.get_friends(**bob) == []


def test_shared_watchlist_requires_friendship(accounts):
    alice, bob, _ = accounts
    alice_id = db.get_or_create_user_profile(**alice)["id"]
    bob_id = db.get_or_create_user_profile(**bob)["id"]

    for identity, movie_ids in ((alice, (550, 551)), (bob, (550, 552))):
        for movie_id in movie_ids:
            db.add_to_watchlist(**identity, movie_id=movie_id)

    with pytest.raises(RuntimeError, match="accepted friend"):
        db.get_shared_watchlist(**alice, friend_user_id=bob_id)

    db.send_friend_request(**alice, target_user_id=bob_id)
    db.accept_friend_request(**bob, requester_user_id=alice_id)
    assert [
        item["movieId"]
        for item in db.get_shared_watchlist(**alice, friend_user_id=bob_id)
    ] == [550]

    db.mark_movie_watched(**bob, movie_id=550)
    assert db.get_shared_watchlist(**alice, friend_user_id=bob_id) == []


@pytest.fixture
def invitation_request(accounts):
    alice, bob, _ = accounts
    alice_id = db.get_or_create_user_profile(**alice)["id"]
    bob_id = db.get_or_create_user_profile(**bob)["id"]
    db.send_friend_request(**alice, target_user_id=bob_id)
    db.accept_friend_request(**bob, requester_user_id=alice_id)
    for identity in (alice, bob):
        db.add_to_watchlist(**identity, movie_id=550)

    starts_at = datetime.now(timezone.utc) + timedelta(days=1)
    return {
        **alice,
        "friend_user_id": bob_id,
        "movie_id": 550,
        "uid": "integration-invitation@moview",
        "starts_at": starts_at,
        "ends_at": starts_at + timedelta(hours=2),
        "timezone": "UTC",
        "event_summary": "Watch Movie",
        "location": None,
        "message": None,
        "idempotency_key": "integration-request",
    }


def test_invitation_idempotency_and_delivery(invitation_request):
    invitation = db.create_movie_invitation(**invitation_request)
    repeated = db.create_movie_invitation(**invitation_request)
    assert repeated["id"] == invitation["id"]
    assert rows("select count(*) from movie_invitations")[0][0] == 1

    conflicting = {
        **invitation_request,
        "ends_at": invitation_request["ends_at"] + timedelta(minutes=30),
    }
    with pytest.raises(RuntimeError, match="idempotency key"):
        db.create_movie_invitation(**conflicting)
    assert rows("select count(*) from movie_invitations")[0][0] == 1

    failed = db.mark_movie_invitation_failed(
        invitation_id=invitation["id"], error_message="test failure",
    )
    assert failed["status"] == "failed"

    sent = db.mark_movie_invitation_sent(
        invitation_id=invitation["id"], provider_message_id="test-provider",
    )
    assert sent["status"] == "sent"
    assert sent["sentAt"] is not None
    assert sent["providerMessageId"] == "test-provider"

    with db._transaction() as cursor:
        cursor.execute(
            "update movie_invitations set status = 'cancelled' where id = %s",
            (invitation["id"],),
        )
    with pytest.raises(RuntimeError, match="not found"):
        db.mark_movie_invitation_sent(
            invitation_id=invitation["id"], provider_message_id="another",
        )
    assert rows("select status from movie_invitations") == (["cancelled"],)


def test_response_failure_rolls_back_invitation(invitation_request, monkeypatch):
    def fail_conversion(row):
        raise RuntimeError("response conversion failed")

    with monkeypatch.context() as scope:
        scope.setattr(db, "_invitation_participant_from_row", fail_conversion)
        with pytest.raises(RuntimeError, match="response conversion failed"):
            db.create_movie_invitation(**invitation_request)

    assert rows("select count(*) from movie_invitations")[0][0] == 0
    assert db.create_movie_invitation(**invitation_request)["status"] == "pending"
