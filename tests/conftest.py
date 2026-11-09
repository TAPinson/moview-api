from collections import OrderedDict

import pytest

from moview_api import movie_details


@pytest.fixture(autouse=True)
def isolate_movie_cache(monkeypatch):
    monkeypatch.setattr(movie_details, "_cache", OrderedDict())
