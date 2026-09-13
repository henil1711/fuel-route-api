import os

os.environ.setdefault("DJANGO_DEBUG", "true")

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def isolated_cache(settings, tmp_path):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.LOCK_DIR = tmp_path / "locks"
    cache.clear()
    from routes.services.station_matcher import _station_index

    _station_index.cache_clear()
