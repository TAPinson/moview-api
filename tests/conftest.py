from copy import deepcopy
from datetime import datetime, timezone

import pytest

from moview_api import movie_details, tmdb


@pytest.fixture(autouse=True)
def movie_store(monkeypatch):
    records = {}

    def load(movie_ids):
        return {
            movie_id: deepcopy(records[movie_id])
            for movie_id in movie_ids
            if movie_id in records
        }

    def save(movies):
        for movie in movies:
            records[movie["id"]] = {
                "movie": deepcopy(movie),
                "updatedAt": datetime.now(timezone.utc),
            }

    monkeypatch.setattr(movie_details, "load_movies", load)
    monkeypatch.setattr(movie_details, "save_movies", save)
    monkeypatch.setattr(tmdb, "save_movies", save)
    return records
