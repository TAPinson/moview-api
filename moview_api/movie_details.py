from __future__ import annotations

import logging
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any
from urllib.error import URLError

from moview_api.movies import load_movies, save_movies
from moview_api.tmdb import get_movie_details


JsonObject = dict[str, Any]

MOVIE_MAX_AGE = timedelta(days=30)
MAX_WORKERS = 4
LOOKUP_BUDGET_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 2
RESPONSE_RESERVE_SECONDS = 1

_logger = logging.getLogger(__name__)
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


def needs_refresh(
    record: JsonObject | None,
    now: datetime,
) -> bool:
    return record is None or record["updatedAt"] < now - MOVIE_MAX_AGE


def _fetch_movie(movie_id: int, deadline: float) -> JsonObject | None:
    remaining = deadline - monotonic()
    if remaining <= 0:
        return None

    try:
        movie = get_movie_details(
            movie_id,
            timeout=min(REQUEST_TIMEOUT_SECONDS, remaining),
        )
        if type(movie.get("id")) is not int or movie["id"] != movie_id:
            raise ValueError("TMDB returned an unexpected movie ID.")
    except (OSError, URLError, ValueError) as error:
        # Exception messages can contain the request URL and API key.
        _logger.warning(
            "Movie details unavailable: movie_id=%s error_type=%s",
            movie_id,
            type(error).__name__,
        )
        return None

    return movie


def enrich_movies(items: list[JsonObject]) -> list[JsonObject]:
    if not items:
        return []

    deadline = _deadline.get()
    if deadline is None:
        deadline = monotonic() + LOOKUP_BUDGET_SECONDS

    movie_ids = list(dict.fromkeys(item["movieId"] for item in items))
    records = load_movies(movie_ids)
    now = datetime.now(timezone.utc)

    movies = {
        movie_id: records[movie_id]["movie"] if movie_id in records else None
        for movie_id in movie_ids
    }
    refresh_ids = iter(
        movie_id
        for movie_id in movie_ids
        if needs_refresh(records.get(movie_id), now)
    )
    refreshed = {}
    pending = {}
    exhausted = False

    try:
        while monotonic() < deadline:
            while len(pending) < MAX_WORKERS and not exhausted:
                movie_id = next(refresh_ids, None)
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
                movie = future.result()
                if movie is not None:
                    movies[movie_id] = movie
                    refreshed[movie_id] = movie
    finally:
        for future in pending:
            future.cancel()

    if refreshed:
        save_movies(list(refreshed.values()))

    return [
        {**item, "movie": deepcopy(movies[item["movieId"]])}
        for item in items
    ]
