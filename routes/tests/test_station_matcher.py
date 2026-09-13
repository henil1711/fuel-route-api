from decimal import Decimal
import pytest
from routes.models import FuelStation
from routes.services.station_matcher import match_stations


@pytest.mark.django_db
def test_projection_distance_and_corridor():
    for opis, lat, lon in [(1, 40, -99.5), (2, 40.01, -99.3), (3, 41, -99.5)]:
        FuelStation.objects.create(
            opis_id=opis,
            name="Test",
            address="Road",
            city="City",
            state="KS",
            retail_price=Decimal("3.33"),
            latitude=lat,
            longitude=lon,
        )
    route = {
        "distance_miles": 100,
        "geometry": {"type": "LineString", "coordinates": [[-100, 40], [-99, 40]]},
    }
    matches, count = match_stations(route, 5)
    assert count == 3
    assert {c.station["opis_id"] for c in matches} == {1, 2}
    first = next(c for c in matches if c.station["opis_id"] == 1)
    assert float(first.mile) == pytest.approx(50, abs=0.2)
    assert first.offset_miles < 0.1


@pytest.mark.django_db
def test_empty_and_zero_length_routes():
    route = {"distance_miles": 0, "geometry": {"type": "LineString", "coordinates": [[-100, 40], [-100, 40]]}}
    assert match_stations(route, 5) == ([], 0)


@pytest.mark.django_db
def test_coordinate_update_invalidates_index():
    station = FuelStation.objects.create(
        opis_id=1, name="Test", address="Road", city="City", state="KS", retail_price=3
    )
    route = {
        "distance_miles": 100,
        "geometry": {"type": "LineString", "coordinates": [[-100, 40], [-99, 40]]},
    }
    assert match_stations(route, 5)[1] == 0
    station.latitude, station.longitude = 40, -99.5
    station.save()
    assert match_stations(route, 5)[1] == 1
