import json

import pytest

from moview_api.handler import lambda_handler
from moview_api.schema import build_movie_response


CLAIMS = {"sub": "alice", "email": "alice@example.com"}


@pytest.fixture
def movie_response(monkeypatch):
    movie = {"id": 550, "title": "Example", "genre_ids": []}

    def enrich(items):
        assert items == [{"movieId": 550}]
        return [{"movieId": 550, "movie": movie}]

    def state(**kwargs):
        assert kwargs == {
            "user_uuid": "alice",
            "email": "alice@example.com",
            "movie_id": 550,
        }
        return {"isLiked": True, "watchlistStatus": "watched"}

    monkeypatch.setattr("moview_api.schema.enrich_movies", enrich)
    monkeypatch.setattr("moview_api.schema.get_movie_user_state", state)
    return {
        "movie": movie,
        "isLiked": True,
        "watchlistStatus": "watched",
    }


def test_appsync_movie(movie_response):
    event = {
        "info": {"fieldName": "movie", "parentTypeName": "Query"},
        "arguments": {"movieId": 550},
        "identity": {"claims": CLAIMS},
    }
    assert lambda_handler(event, None) == movie_response


def test_http_movie(movie_response):
    event = {
        "identity": {"claims": CLAIMS},
        "body": json.dumps({
            "query": """
                query {
                  movie(movieId: 550) {
                    movie { id title genre_ids }
                    isLiked
                    watchlistStatus
                  }
                }
            """,
        }),
    }
    response = lambda_handler(event, None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"data": {"movie": movie_response}}


def test_movie_requires_identity():
    with pytest.raises(RuntimeError, match="Authenticated user identity"):
        build_movie_response({}, 550)


@pytest.mark.parametrize("movie_id", [0, -1, True, None, "550"])
def test_movie_rejects_invalid_id(movie_id):
    with pytest.raises(RuntimeError, match="positive movie ID"):
        build_movie_response(CLAIMS, movie_id)


def test_movie_unavailable(monkeypatch):
    monkeypatch.setattr(
        "moview_api.schema.enrich_movies",
        lambda items: [{"movieId": 550, "movie": None}],
    )
    assert build_movie_response(CLAIMS, 550) is None
