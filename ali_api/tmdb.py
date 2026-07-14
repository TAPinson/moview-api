from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
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


def _movie_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "poster_path": result.get("poster_path"),
        "adult": result.get("adult"),
        "overview": result.get("overview"),
        "release_date": result.get("release_date"),
        "genre_ids": result.get("genre_ids") or [],
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
