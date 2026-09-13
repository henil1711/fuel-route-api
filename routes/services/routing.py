import logging
import math

import requests
from django.conf import settings
from django.core.cache import cache
from routes.exceptions import PlanningError, ProviderError
from .cache import cache_key, request_lock

METERS_PER_MILE = 1609.344
logger = logging.getLogger(__name__)


def get_route(start: dict, finish: dict) -> tuple[dict, bool]:
    coordinates = ";".join(f"{p['longitude']:.6f},{p['latitude']:.6f}" for p in (start, finish))
    key = cache_key("osrm:v1", [settings.OSRM_BASE_URL, coordinates])
    cached = cache.get(key)
    if cached is not None:
        return cached, True
    with request_lock(key):
        cached = cache.get(key)
        if cached is not None:
            return cached, True
        try:
            response = requests.get(
                f"{settings.OSRM_BASE_URL}/route/v1/driving/{coordinates}",
                params={
                    "overview": "full",
                    "geometries": "geojson",
                    "steps": "false",
                    "alternatives": "false",
                },
                headers={"User-Agent": settings.GEOCODING_USER_AGENT},
                timeout=settings.HTTP_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") in {"NoRoute", "NoSegment"}:
                raise PlanningError("No driving route is available between these locations.")
            if data.get("code") != "Ok":
                raise ValueError("Invalid OSRM response")
            route = data["routes"][0]
            distance, duration = float(route["distance"]), float(route["duration"])
            geometry = route["geometry"]
            points = geometry["coordinates"]
            if (
                not math.isfinite(distance)
                or not math.isfinite(duration)
                or distance < 0
                or duration < 0
                or geometry["type"] != "LineString"
                or len(points) < 2
            ):
                raise ValueError("Invalid route")
            for lon, lat in points:
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError("Invalid route geometry")
            result = {
                "distance_miles": distance / METERS_PER_MILE,
                "duration_minutes": duration / 60,
                "geometry": geometry,
            }
        except (
            requests.RequestException,
            KeyError,
            ValueError,
            IndexError,
            TypeError,
            AttributeError,
        ) as exc:
            logger.warning("Routing provider failed (%s)", type(exc).__name__)
            raise ProviderError() from exc
        cache.set(key, result, settings.CACHE_TIMEOUT)
        return result, False
