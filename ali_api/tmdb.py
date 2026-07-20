from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TMDB_MOVIE_URL = "https://api.themoviedb.org/3/movie"
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie"
TMDB_SECRET_KEYS = ("TMDB_API_KEY", "tmdb_api_key", "tmdbApiKey", "api_key", "apiKey", "api-key", "key")


def search_movies(query: str) -> list[dict[str, Any]]:
    normalized_query = query.strip()
    if not normalized_query:
        return []

    params = urlencode({"query": normalized_query, "api_key": _tmdb_api_key()})
    request = Request(
        f"{TMDB_SEARCH_URL}?{params}",
        headers={"accept": "application/json", "user-agent": "moview-api"},
    )

    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    results = payload.get("results", [])
    if not isinstance(results, list):
        return []

    return [_movie_result(result) for result in results if isinstance(result, dict)]


def discover_movies_by_genre(genre_id: int, page: int = 1) -> dict[str, Any]:
    if not isinstance(genre_id, int) or genre_id <= 0:
        raise ValueError("Genre ID must be a positive integer.")
    if not isinstance(page, int) or page < 1 or page > 500:
        raise ValueError("Page must be between 1 and 500.")

    params = urlencode({
        "with_genres": genre_id,
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "include_video": "false",
        "page": page,
        "api_key": _tmdb_api_key(),
    })
    request = Request(
        f"{TMDB_DISCOVER_URL}?{params}",
        headers={"accept": "application/json", "user-agent": "moview-api"},
    )

    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    results = payload.get("results", [])
    if not isinstance(results, list):
        results = []

    return {
        "page": payload.get("page", page),
        "totalPages": payload.get("total_pages", 1),
        "results": [
            _movie_result(result) for result in results if isinstance(result, dict)
        ],
    }


def get_movie_details(movie_id: int) -> dict[str, Any]:
    params = urlencode({"api_key": _tmdb_api_key()})
    request = Request(
        f"{TMDB_MOVIE_URL}/{movie_id}?{params}",
        headers={"accept": "application/json", "user-agent": "moview-api"},
    )

    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise RuntimeError("TMDB movie details response was not an object.")

    return _movie_result(payload)


def _movie_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "poster_path": result.get("poster_path"),
        "adult": result.get("adult"),
        "overview": result.get("overview"),
        "release_date": result.get("release_date"),
        "genre_ids": _genre_ids(result),
        "id": result.get("id"),
        "original_title": result.get("original_title"),
        "original_language": result.get("original_language"),
        "title": result.get("title"),
        "backdrop_path": result.get("backdrop_path"),
        "popularity": result.get("popularity"),
        "vote_count": result.get("vote_count"),
        "video": result.get("video"),
        "vote_average": result.get("vote_average"),
    }


def _genre_ids(result: dict[str, Any]) -> list[int]:
    genre_ids = result.get("genre_ids")
    if isinstance(genre_ids, list):
        return [genre_id for genre_id in genre_ids if isinstance(genre_id, int)]

    genres = result.get("genres")
    if not isinstance(genres, list):
        return []

    return [
        genre.get("id")
        for genre in genres
        if isinstance(genre, dict) and isinstance(genre.get("id"), int)
    ]


def _tmdb_api_key() -> str:
    secret_id = os.environ.get("TMDB_API_KEY_SECRET_ID", "dev/tmdb-api-key")
    return _tmdb_api_key_from_secret(secret_id)


@lru_cache(maxsize=1)
def _tmdb_api_key_from_secret(secret_id: str) -> str:
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    secret = response.get("SecretString")
    if not secret:
        raise RuntimeError("TMDB API key secret must be stored as SecretString.")

    return _parse_tmdb_secret(secret)


def _parse_tmdb_secret(secret: str) -> str:
    try:
        parsed: Any = json.loads(secret)
    except json.JSONDecodeError:
        return secret

    if isinstance(parsed, str):
        return parsed

    if isinstance(parsed, dict):
        for key in TMDB_SECRET_KEYS:
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value

        string_values = [value for value in parsed.values() if isinstance(value, str) and value]
        if len(string_values) == 1:
            return string_values[0]

    raise RuntimeError(
        "TMDB API key secret must be plaintext, JSON with an api_key field, "
        "or JSON with exactly one string value."
    )
