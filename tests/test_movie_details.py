from collections import Counter
from concurrent.futures import ThreadPoolExecutor
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


def test_cache_expires_and_returns_independent_values(monkeypatch):
    clock = [0.0]
    calls = []

    def fetch(movie_id, *, timeout):
        calls.append(movie_id)
        return {"id": movie_id, "genre_ids": [1]}

    monkeypatch.setattr(details, "monotonic", lambda: clock[0])
    monkeypatch.setattr(details, "get_movie_details", fetch)

    first = details.enrich_movies([{"movieId": 1}])
    first[0]["movie"]["genre_ids"].append(99)

    second = details.enrich_movies([{"movieId": 1}])
    assert second[0]["movie"]["genre_ids"] == [1]
    assert calls == [1]

    clock[0] = details.CACHE_TTL_SECONDS + 1
    details.enrich_movies([{"movieId": 1}])
    assert calls == [1, 1]


def test_cache_evicts_least_recently_used_movie(monkeypatch):
    calls = Counter()

    def fetch(movie_id, *, timeout):
        calls[movie_id] += 1
        return {"id": movie_id}

    monkeypatch.setattr(details, "CACHE_LIMIT", 2)
    monkeypatch.setattr(details, "get_movie_details", fetch)

    for movie_id in [1, 2, 1, 3, 1, 2]:
        details.enrich_movies([{"movieId": movie_id}])

    assert calls == {1: 1, 2: 2, 3: 1}
    assert len(details._cache) == 2


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
