from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from moview_api.db import _transaction


MOVIE_FIELDS = (
    "id",
    "poster_path",
    "adult",
    "overview",
    "release_date",
    "genre_ids",
    "original_title",
    "original_language",
    "title",
    "backdrop_path",
    "popularity",
    "vote_count",
    "video",
    "vote_average",
)


def load_movies(movie_ids: list[int]) -> dict[int, dict[str, Any]]:
    movie_ids = list(dict.fromkeys(movie_ids))
    if not movie_ids:
        return {}

    columns = ", ".join(MOVIE_FIELDS)
    with _transaction() as cursor:
        cursor.execute(
            f"""
            select {columns}, updated_at
            from movies
            where id = any(%s::integer[])
            """,
            (movie_ids,),
        )
        rows = cursor.fetchall()

    records = {}
    for row in rows:
        movie = dict(zip(MOVIE_FIELDS, row[:-1], strict=True))
        release_date = movie["release_date"]
        if release_date is not None:
            movie["release_date"] = release_date.isoformat()
        records[movie["id"]] = {
            "movie": movie,
            "updatedAt": row[-1],
        }
    return records


def save_movies(movies: list[dict[str, Any]]) -> None:
    unique_movies = {
        movie["id"]: movie
        for movie in movies
        if type(movie.get("id")) is int and movie["id"] > 0
    }
    if not unique_movies:
        return

    updated_at = datetime.now(timezone.utc)
    parameters = []
    for movie in unique_movies.values():
        values = {field: movie.get(field) for field in MOVIE_FIELDS}
        values["genre_ids"] = movie.get("genre_ids") or []
        release_date = movie.get("release_date")
        values["release_date"] = (
            date.fromisoformat(release_date) if release_date else None
        )
        parameters.extend(values[field] for field in MOVIE_FIELDS)
        parameters.append(updated_at)

    columns = ", ".join((*MOVIE_FIELDS, "updated_at"))
    row_placeholder = "(" + ", ".join(
        ["%s"] * (len(MOVIE_FIELDS) + 1)
    ) + ")"
    placeholders = ", ".join([row_placeholder] * len(unique_movies))
    updates = ", ".join(
        f"{field} = excluded.{field}"
        for field in (*MOVIE_FIELDS[1:], "updated_at")
    )

    with _transaction() as cursor:
        cursor.execute(
            f"""
            insert into movies ({columns})
            values {placeholders}
            on conflict (id) do update
            set {updates}
            where movies.updated_at <= excluded.updated_at
            """,
            tuple(parameters),
        )
