from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from urllib.error import URLError

import pytest

from moview_api import movie_details as details


def test_parallel_loading_preserves_order_and_deduplicates(monkeypatch):
    barrier = Barrier(4)

    def fetch(movie_id, *, timeout):
        barrier.wait(timeout=2)
        return {"id": movie_id}

    monkeypatch.setattr(details, "get_movie_details", fetch)
    items = [{"movieId": value} for value in [4, 2, 1, 3, 4]]

    result = details.enrich_movies(items)

    assert [item["movie"]["id"] for item in result] == [4, 2, 1, 3, 4]
    assert items == [{"movieId": value} for value in [4, 2, 1, 3, 4]]


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(days=29), False),
        (timedelta(days=30), False),
        (timedelta(days=30, microseconds=1), True),
    ],
)
def test_refresh_boundary(age, expected):
    now = datetime(2026, 11, 17, tzinfo=timezone.utc)
    record = {"updatedAt": now - age}
    assert details.needs_refresh(record, now) is expected
    assert details.needs_refresh(None, now) is True


def test_stored_movie_returns_independent_values(monkeypatch, movie_store):
    movie_store[1] = {
        "movie": {"id": 1, "genre_ids": [1]},
        "updatedAt": datetime.now(timezone.utc),
    }

    def unexpected_fetch(*args, **kwargs):
        pytest.fail("Fresh movies should not require TMDB")

    monkeypatch.setattr(details, "get_movie_details", unexpected_fetch)

    first = details.enrich_movies([{"movieId": 1}])
    first[0]["movie"]["genre_ids"].append(99)
    second = details.enrich_movies([{"movieId": 1}])
    assert second[0]["movie"]["genre_ids"] == [1]


def test_expired_movie_is_refreshed_and_saved(monkeypatch, movie_store):
    old_date = datetime.now(timezone.utc) - timedelta(days=31)
    movie_store[1] = {
        "movie": {"id": 1, "title": "Old"},
        "updatedAt": old_date,
    }
    monkeypatch.setattr(
        details, "get_movie_details",
        lambda movie_id, *, timeout: {"id": movie_id, "title": "New"},
    )

    result = details.enrich_movies([{"movieId": 1}])

    assert result[0]["movie"]["title"] == "New"
    assert movie_store[1]["movie"]["title"] == "New"
    assert movie_store[1]["updatedAt"] > old_date


def test_failed_refresh_keeps_old_movie_and_timestamp(monkeypatch, movie_store):
    old_date = datetime.now(timezone.utc) - timedelta(days=31)
    movie_store[1] = {
        "movie": {"id": 1, "title": "Old"},
        "updatedAt": old_date,
    }

    def fetch(movie_id, *, timeout):
        raise URLError("upstream unavailable")

    monkeypatch.setattr(details, "get_movie_details", fetch)
    result = details.enrich_movies([{"movieId": 1}])

    assert result[0]["movie"]["title"] == "Old"
    assert movie_store[1]["updatedAt"] == old_date


def test_bulk_read_and_write(monkeypatch):
    reads = []
    writes = []

    def load(movie_ids):
        reads.append(movie_ids)
        return {}

    monkeypatch.setattr(details, "load_movies", load)
    monkeypatch.setattr(details, "save_movies", writes.append)
    monkeypatch.setattr(
        details, "get_movie_details",
        lambda movie_id, *, timeout: {"id": movie_id},
    )

    details.enrich_movies([{"movieId": 1}, {"movieId": 2}, {"movieId": 1}])

    assert reads == [[1, 2]]
    assert len(writes) == 1
    assert {movie["id"] for movie in writes[0]} == {1, 2}


def test_failed_lookup_preserves_entry_and_is_not_cached(monkeypatch):
    calls = []

    def fetch(movie_id, *, timeout):
        calls.append(movie_id)
        if movie_id == 2:
            raise URLError("upstream unavailable")
        return {"id": movie_id}

    monkeypatch.setattr(details, "get_movie_details", fetch)
    items = [{"movieId": 1}, {"movieId": 2, "notes": "Keep this"}]

    result = details.enrich_movies(items)
    assert result == [
        {"movieId": 1, "movie": {"id": 1}},
        {"movieId": 2, "notes": "Keep this", "movie": None},
    ]

    details.enrich_movies(items)
    assert Counter(calls) == {1: 1, 2: 2}


def test_mismatched_movie_id_is_not_saved(monkeypatch, movie_store):
    monkeypatch.setattr(
        details, "get_movie_details",
        lambda movie_id, *, timeout: {"id": movie_id + 1},
    )
    assert details.enrich_movies([{"movieId": 1}]) == [
        {"movieId": 1, "movie": None},
    ]
    assert movie_store == {}


def test_unexpected_errors_are_not_hidden(monkeypatch):
    def fetch(movie_id, *, timeout):
        raise TypeError("programming error")

    monkeypatch.setattr(details, "get_movie_details", fetch)
    with pytest.raises(TypeError, match="programming error"):
        details.enrich_movies([{"movieId": 1}])


def test_deadline_does_not_wait_for_running_lookup(monkeypatch):
    release = Event()
    finished = Event()

    def fetch(movie_id, *, timeout):
        try:
            release.wait(timeout=2)
            return {"id": movie_id}
        finally:
            finished.set()

    monkeypatch.setattr(details, "get_movie_details", fetch)
    monkeypatch.setattr(details, "LOOKUP_BUDGET_SECONDS", 0.05)

    with ThreadPoolExecutor(max_workers=1) as caller:
        future = caller.submit(details.enrich_movies, [{"movieId": 1}])
        try:
            assert future.result(timeout=1) == [{"movieId": 1, "movie": None}]
        finally:
            release.set()
            future.result(timeout=2)
            assert finished.wait(timeout=2)


def test_budget_reserves_time_for_lambda_response(monkeypatch):
    class Context:
        def get_remaining_time_in_millis(self):
            return 500

    def unexpected_fetch(*args, **kwargs):
        pytest.fail("No request should start without enough time remaining")

    monkeypatch.setattr(details, "get_movie_details", unexpected_fetch)

    with details.movie_details_budget(Context()):
        assert details.enrich_movies([{"movieId": 1}]) == [
            {"movieId": 1, "movie": None},
        ]

    assert details._deadline.get() is None
