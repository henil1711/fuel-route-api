import json
from decimal import Decimal

import pytest
from django.core.management import call_command
from routes.models import FuelStation


def station(opis, name, city="Test City"):
    return FuelStation.objects.create(
        opis_id=opis, name=name, city=city, state="TX", address="Road", retail_price=Decimal("3.10")
    )


def poi(id_, ref=None, lon=-100, city="Test City"):
    tags = {"amenity": "fuel", "brand": "Pilot", "addr:city": city, "addr:state": "TX"}
    if ref is not None:
        tags["ref"] = str(ref)
    return {"id": id_, "type": "node", "lat": 30, "lon": lon, "tags": tags}


@pytest.mark.django_db
def test_bulk_match_methods_and_ambiguity(tmp_path):
    station(1, "PILOT #123", "Exact City")
    station(2, "PILOT #456", "Unique City")
    station(3, "PILOT #789", "Ambiguous City")
    station(4, "PILOT #999", "Conflict City")
    payload = {
        "elements": [
            poi(1, 123, city="Exact City"),
            poi(2, city="Unique City"),
            poi(3, city="Ambiguous City"),
            poi(4, lon=-101, city="Ambiguous City"),
            poi(5, 888, city="Conflict City"),
        ]
    }
    path = tmp_path / "osm.json"
    path.write_text(json.dumps(payload))
    output = tmp_path / "coordinates.csv"
    call_command("locate_stations", osm_file=str(path), output=str(output))
    assert FuelStation.objects.get(pk=1).latitude == 30
    assert "exact chain/store ref" in FuelStation.objects.get(pk=1).coordinate_source
    assert "approximate identity" in FuelStation.objects.get(pk=2).coordinate_source
    assert FuelStation.objects.get(pk=3).latitude is None
    assert FuelStation.objects.get(pk=4).latitude is None
