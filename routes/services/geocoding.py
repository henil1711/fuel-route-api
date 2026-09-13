import logging
import math
import time

import requests
from django.conf import settings
from django.core.cache import cache
from routes.exceptions import LocationError, ProviderError
from .cache import cache_key, request_lock

logger = logging.getLogger(__name__)


def geocode(location: str) -> dict:
    """Only endpoint locations; never called for the station dataset at request time."""
    query = " ".join(location.split())
    key = cache_key("geocode:v1", [settings.GEOCODING_BASE_URL, query.casefold()])
    cached = cache.get(key)
    if cached is not None:
        return {**cached, "input": location}
    # Serialize all geocoder traffic and hold the lock during I/O. Shared by workers.
    with request_lock("geocoding-provider"):
        cached = cache.get(key)
        if cached is not None:
            return {**cached, "input": location}
        stamp = settings.LOCK_DIR / "geocoding-last-request"
        last = float(stamp.read_text()) if stamp.exists() else 0
        time.sleep(max(0, 1.1 - (time.time() - last)))
        stamp.write_text(str(time.time()))
        try:
            response = requests.get(
                settings.GEOCODING_BASE_URL + "/search",
                params={"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 1},
                headers={"User-Agent": settings.GEOCODING_USER_AGENT},
                timeout=settings.HTTP_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError("Expected a list")
            if not data:
                raise LocationError("Location could not be found. Include a US city and state.")
            item = data[0]
            if item["address"].get("country_code", "").lower() != "us":
                raise LocationError("Both locations must be within the United States.")
            lat, lon = float(item["lat"]), float(item["lon"])
            if (
                not math.isfinite(lat)
                or not math.isfinite(lon)
                or not (-90 <= lat <= 90 and -180 <= lon <= 180)
            ):
                raise ValueError("Invalid provider coordinates")
            result = {"latitude": lat, "longitude": lon, "display_name": item.get("display_name", query)}
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("Geocoding provider failed (%s)", type(exc).__name__)
            raise ProviderError() from exc
        cache.set(key, result, settings.GEOCODING_CACHE_TIMEOUT)
        return {**result, "input": location}
