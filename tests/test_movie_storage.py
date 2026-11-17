import json
from unittest.mock import MagicMock

import pytest

from moview_api import tmdb


@pytest.mark.parametrize("operation", ["search", "browse"])
def test_movie_results_are_saved(monkeypatch, movie_store, operation):
    response = MagicMock()
    response.read.return_value = json.dumps({
        "page": 1,
        "total_pages": 2,
        "results": [
            {
                "id": 550,
                "title": "Example",
                "release_date": "",
                "genre_ids": [18],
            },
        ],
    }).encode()
    request = MagicMock()
    request.__enter__.return_value = response

    monkeypatch.setattr(tmdb, "_tmdb_api_key", lambda: "test-key")
    monkeypatch.setattr(tmdb, "urlopen", lambda *args, **kwargs: request)

    if operation == "search":
        result = tmdb.search_movies("Example")
    else:
        page = tmdb.discover_movies_by_genre(18)
        assert page["totalPages"] == 2
        result = page["results"]

    assert movie_store[550]["movie"] == result[0]
    assert movie_store[550]["movie"]["genre_ids"] == [18]
