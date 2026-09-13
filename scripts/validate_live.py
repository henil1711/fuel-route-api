"""Opt-in real provider validation. Unit tests never use the network."""
# ruff: noqa: E402 -- Django must initialize before importing models.

import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
import requests
from django.conf import settings
from django.core.cache import cache
from django.test import Client
from routes.models import FuelStation
from routes.services.cache import cache_key
from routes.services.geocoding import geocode


def main():
    output = settings.BASE_DIR / "docs"
    output.mkdir(exist_ok=True)
    report = []
    client = Client(HTTP_HOST="localhost")
    for label, finish in [("short", "Newark, NJ"), ("chicago", "Chicago, IL"), ("long", "Dallas, TX")]:
        start_text = "New York, NY"
        start, end = geocode(start_text), geocode(finish)
        coords = ";".join(f"{p['longitude']:.6f},{p['latitude']:.6f}" for p in (start, end))
        cache.delete(cache_key("osrm:v1", [settings.OSRM_BASE_URL, coords]))
        timings, calls = [], []
        for iteration in range(2):
            with patch("requests.get", wraps=requests.get) as observed:
                t = time.perf_counter()
                result = client.post(
                    "/api/v1/route/",
                    data=json.dumps({"start": start_text, "finish": finish}),
                    content_type="application/json",
                )
                timings.append(round(time.perf_counter() - t, 4))
            calls.append(len(observed.call_args_list))
            assert result.status_code == 200, result.content[:1000]
            data = result.json()
            assert data["route"]["geometry"]["type"] == "LineString"
            assert len(data["route"]["geometry"]["coordinates"]) >= 2
            assert data["metadata"]["route_cache_hit"] == bool(iteration)
            if iteration == 0:
                (output / f"live-{label}-response.json").write_text(
                    json.dumps(data, indent=2), encoding="utf-8"
                )
        assert calls == [1, 0], calls  # This counts real outgoing HTTP requests, not response metadata.
        total = Decimal(0)
        for stop in data["fuel_stops"]:
            station = FuelStation.objects.get(pk=stop["opis_id"])
            assert station.retail_price == Decimal(stop["price_per_gallon"])
            assert station.prices.exists()
            assert station.latitude == stop["latitude"] and station.longitude == stop["longitude"]
            assert 0 <= Decimal(stop["arrival_fuel_gallons"]) <= Decimal(stop["remaining_fuel_gallons"]) <= 50
            total += Decimal(stop["fuel_cost"])
        assert total == Decimal(data["fuel_summary"]["total_fuel_cost"])
        if label == "short":
            assert not data["fuel_stops"]
        if label == "long":
            assert len(data["fuel_stops"]) >= 2
        summary = {
            "route": label,
            "start": start_text,
            "finish": finish,
            "status": 200,
            "seconds_miss_hit": timings,
            "actual_http_calls_miss_hit": calls,
            "fuel_stops": len(data["fuel_stops"]),
            "geometry_points": len(data["route"]["geometry"]["coordinates"]),
            "summary": data["fuel_summary"],
        }
        report.append(summary)
        print(json.dumps(summary), flush=True)
    (output / "live-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
