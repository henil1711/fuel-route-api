from decimal import Decimal
from django.conf import settings
from .geocoding import geocode
from .routing import get_route
from .station_matcher import match_stations
from .fuel_optimizer import optimize


def plan_route(start_input: str, finish_input: str) -> dict:
    start, finish = geocode(start_input), geocode(finish_input)
    route, cache_hit = get_route(start, finish)
    candidates, located = match_stations(route, settings.MAX_STATION_ROUTE_DISTANCE_MILES)
    max_range, mpg = Decimal(settings.VEHICLE_MAX_RANGE_MILES), Decimal(settings.VEHICLE_MPG)
    plan = optimize(Decimal(str(route["distance_miles"])), candidates, max_range, mpg)
    return {
        "start": start,
        "finish": finish,
        "route": route,
        "vehicle": {
            "max_range_miles": str(max_range),
            "mpg": str(mpg),
            "tank_capacity_gallons": str(max_range / mpg),
        },
        **plan,
        "metadata": {
            "route_cache_hit": cache_hit,
            "candidate_stations": len(candidates),
            "located_stations": located,
            "routing_calls_this_request": 0 if cache_hit else 1,
            "price_policy": "minimum observed CSV price per OPIS ID; observations have no dates or fuel grades",
            "assumptions": [
                "Starts with a full tank; initial fuel is not charged.",
                "Fuel optimization excludes station access detours and road-access restrictions.",
                "Only locally located CSV stations participate; missing stations can affect feasibility and optimality.",
                "Optimal for the chosen OSRM route, not across alternative routes.",
            ],
            "attribution": "Route and location data © OpenStreetMap contributors; routing by OSRM.",
        },
    }
