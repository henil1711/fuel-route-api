from unittest.mock import Mock, patch
import pytest
import requests
from rest_framework.test import APIClient
from routes.services.geocoding import geocode
from routes.services.routing import get_route
from routes.exceptions import ProviderError


def response(data):
    result = Mock()
    result.json.return_value = data
    return result


def location(country="us"):
    return [
        {"lat": "40.7128", "lon": "-74.006", "address": {"country_code": country}, "display_name": "New York"}
    ]


def route_data():
    return {
        "code": "Ok",
        "routes": [
            {
                "distance": 100000,
                "duration": 3600,
                "geometry": {"type": "LineString", "coordinates": [[-74.006, 40.7128], [-73.5, 40.9]]},
            }
        ],
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"start": "", "finish": "NY"},
        {"start": "a" * 201, "finish": "NY"},
        {"start": [1, 2], "finish": "NY"},
        {"start": 123, "finish": "NY"},
        {"start": None, "finish": "NY"},
    ],
)
def test_api_input_validation_without_external_calls(payload):
    with patch("requests.get") as get:
        result = APIClient().post("/api/v1/route/", payload, format="json")
        assert result.status_code == 400
        assert "error" in result.json()
        get.assert_not_called()


@pytest.mark.django_db
def test_full_api_schema_and_external_call_caching():
    with (
        patch(
            "requests.get", side_effect=[response(location()), response(location()), response(route_data())]
        ) as get,
        patch("time.sleep"),
    ):
        client = APIClient()
        first = client.post(
            "/api/v1/route/", {"start": "New York, NY", "finish": "Nearby, NY"}, format="json"
        )
        assert first.status_code == 200, first.json()
        data = first.json()
        assert data["route"]["geometry"]["type"] == "LineString"
        assert data["fuel_stops"] == []
        assert data["fuel_summary"]["total_fuel_cost"] == "0.00"
        assert data["metadata"]["routing_calls_this_request"] == 1
        second = client.post(
            "/api/v1/route/", {"start": "New York, NY", "finish": "Nearby, NY"}, format="json"
        )
        assert second.status_code == 200
        assert second.json()["metadata"]["routing_calls_this_request"] == 0
        assert get.call_count == 3
        routing_calls = [c for c in get.call_args_list if "/route/v1/driving/" in c.args[0]]
        assert len(routing_calls) == 1
        assert routing_calls[0].kwargs["params"]["geometries"] == "geojson"


@pytest.mark.django_db
@pytest.mark.parametrize("data", [[], location("ca")])
def test_invalid_or_foreign_location_returns_400(data):
    with patch("requests.get", return_value=response(data)):
        result = APIClient().post(
            "/api/v1/route/", {"start": "Toronto, Canada", "finish": "Chicago, IL"}, format="json"
        )
    assert result.status_code == 400


@pytest.mark.django_db
def test_provider_timeout_returns_503():
    with patch("requests.get", side_effect=requests.Timeout):
        result = APIClient().post(
            "/api/v1/route/", {"start": "New York, NY", "finish": "Chicago, IL"}, format="json"
        )
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "provider_unavailable"


@pytest.mark.parametrize(
    "data", [{}, [{"bad": "data"}], [{"lat": "NaN", "lon": "0", "address": {"country_code": "us"}}]]
)
def test_malformed_geocoder_response(data):
    with patch("requests.get", return_value=response(data)), pytest.raises(ProviderError):
        geocode("Bad response, NY")


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"code": "Ok", "routes": []},
        {
            "code": "Ok",
            "routes": [
                {
                    "distance": float("nan"),
                    "duration": 0,
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [0, 0]]},
                }
            ],
        },
    ],
)
def test_malformed_route_response(data):
    with patch("requests.get", return_value=response(data)), pytest.raises(ProviderError):
        get_route({"latitude": 40, "longitude": -80}, {"latitude": 41, "longitude": -81})


def test_geocoder_cache_normalizes_spaces_and_case():
    with patch("requests.get", return_value=response(location())) as get:
        geocode("New York, NY")
        geocode(" new   york, ny ")
        assert get.call_count == 1


@pytest.mark.django_db
def test_impossible_long_route_has_meaningful_error():
    data = route_data()
    data["routes"][0]["distance"] = 1609344
    with (
        patch("requests.get", side_effect=[response(location()), response(location()), response(data)]),
        patch("time.sleep"),
    ):
        result = APIClient().post(
            "/api/v1/route/", {"start": "New York, NY", "finish": "Chicago, IL"}, format="json"
        )
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "infeasible_route"


@pytest.mark.django_db
def test_map_page_and_health():
    page = APIClient().get("/route/")
    assert page.status_code == 200
    assert page["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert APIClient().get("/health/").json() == {"status": "ok"}


def test_routing_timeout_does_not_retry():
    with patch("requests.get", side_effect=requests.Timeout) as get, pytest.raises(ProviderError):
        get_route({"latitude": 40, "longitude": -80}, {"latitude": 41, "longitude": -81})
    assert get.call_count == 1


def test_concurrent_route_miss_makes_one_call():
    import time
    from concurrent.futures import ThreadPoolExecutor

    def provider(*args, **kwargs):
        time.sleep(0.03)
        return response(route_data())

    def run():
        return get_route({"latitude": 40, "longitude": -80}, {"latitude": 41, "longitude": -81})

    with patch("requests.get", side_effect=provider) as get, ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert get.call_count == 1
    assert sorted(hit for _, hit in results) == [False, True]
