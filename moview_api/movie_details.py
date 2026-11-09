from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from threading import Lock
from time import monotonic
from typing import Any
from urllib.error import URLError

from moview_api.tmdb import get_movie_details


JsonObject = dict[str, Any]

CACHE_LIMIT = 500
CACHE_TTL_SECONDS = 3600
MAX_WORKERS = 4
LOOKUP_BUDGET_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 2
RESPONSE_RESERVE_SECONDS = 1

_logger = logging.getLogger(__name__)
_cache: OrderedDict[int, tuple[float, JsonObject]] = OrderedDict()
_cache_lock = Lock()
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_deadline: ContextVar[float | None] = ContextVar(
    "movie_details_deadline", default=None,
)


@contextmanager
def movie_details_budget(context: Any) -> Iterator[None]:
    budget = LOOKUP_BUDGET_SECONDS
    remaining_time = getattr(context, "get_remaining_time_in_millis", None)
    if callable(remaining_time):
        budget = min(
            budget,
            max(0, remaining_time() / 1000 - RESPONSE_RESERVE_SECONDS),
        )

    token = _deadline.set(monotonic() + budget)
    try:
        yield
    finally:
        _deadline.reset(token)


def _cached_movie(movie_id: int) -> JsonObject | None:
    with _cache_lock:
        cached = _cache.get(movie_id)
        if cached is None:
            return None

        expires_at, movie = cached
        if expires_at <= monotonic():
            del _cache[movie_id]
            return None

        _cache.move_to_end(movie_id)
        return deepcopy(movie)


def _fetch_movie(movie_id: int, deadline: float) -> JsonObject | None:
    remaining = deadline - monotonic()
    if remaining <= 0:
        return None

    try:
        movie = get_movie_details(
            movie_id,
            timeout=min(REQUEST_TIMEOUT_SECONDS, remaining),
        )
    except (OSError, URLError, ValueError) as error:
        # Exception messages can contain the request URL and API key.
        _logger.warning(
            "Movie details unavailable: movie_id=%s error_type=%s",
            movie_id,
            type(error).__name__,
        )
        return None

    now = monotonic()
    with _cache_lock:
        expired_ids = [
            key
            for key, (expires_at, _) in _cache.items()
            if expires_at <= now
        ]
        for key in expired_ids:
            del _cache[key]

        _cache[movie_id] = (now + CACHE_TTL_SECONDS, deepcopy(movie))
        _cache.move_to_end(movie_id)
        while len(_cache) > CACHE_LIMIT:
            _cache.popitem(last=False)

    return movie


def enrich_movies(items: list[JsonObject]) -> list[JsonObject]:
    if not items:
        return []

    deadline = _deadline.get()
    if deadline is None:
        deadline = monotonic() + LOOKUP_BUDGET_SECONDS

    movies = {
        movie_id: _cached_movie(movie_id)
        for movie_id in dict.fromkeys(item["movieId"] for item in items)
    }
    missing_ids = iter(
        movie_id for movie_id, movie in movies.items() if movie is None
    )
    pending = {}
    exhausted = False

    try:
        while monotonic() < deadline:
            while len(pending) < MAX_WORKERS and not exhausted:
                movie_id = next(missing_ids, None)
                if movie_id is None:
                    exhausted = True
                else:
                    future = _executor.submit(_fetch_movie, movie_id, deadline)
                    pending[future] = movie_id

            if not pending:
                break

            completed, _ = wait(
                pending,
                timeout=max(0, deadline - monotonic()),
                return_when=FIRST_COMPLETED,
            )
            if not completed:
                break

            for future in completed:
                movie_id = pending.pop(future)
                movies[movie_id] = future.result()
    finally:
        for future in pending:
            future.cancel()

    return [
        {**item, "movie": deepcopy(movies[item["movieId"]])}
        for item in items
    ]
