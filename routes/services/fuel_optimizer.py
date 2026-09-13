"""Exact continuous-fuel greedy optimum for an ordered, detour-free route."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from routes.exceptions import PlanningError

D = Decimal
EPSILON = D("0.000000001")


@dataclass(frozen=True)
class Candidate:
    station: dict
    mile: Decimal
    offset_miles: float
    price: Decimal


def quantity(value: Decimal) -> str:
    return str(value.quantize(D("0.000001"), rounding=ROUND_HALF_UP))


def money(value: Decimal) -> str:
    return str(value.quantize(D("0.01"), rounding=ROUND_HALF_UP))


def optimize(
    distance: Decimal, candidates: list[Candidate], max_range: Decimal = D(500), mpg: Decimal = D(10)
) -> dict:
    """O(n log n) sorting + O(n) next-cheaper lookup and simulation.

    Fuel is continuous. Passing a candidate without buying is not a stop. Money is
    Decimal throughout; posted stop costs are rounded to cents, then summed.
    """
    if (
        not all(v.is_finite() for v in (distance, max_range, mpg))
        or distance < 0
        or max_range <= 0
        or mpg <= 0
    ):
        raise ValueError("Distance must be nonnegative; vehicle parameters must be positive and finite")
    tank = max_range / mpg
    for c in candidates:
        if not c.mile.is_finite() or not c.price.is_finite() or c.price <= 0:
            raise ValueError("Invalid station distance or price")
    points = sorted(
        (c for c in candidates if 0 <= c.mile < distance),
        key=lambda c: (c.mile, c.price, c.station["opis_id"]),
    )
    cheaper: list[int | None] = [None] * len(points)
    stack: list[int] = []
    for i in range(len(points) - 1, -1, -1):
        while stack and points[stack[-1]].price >= points[i].price:
            stack.pop()
        if stack:
            cheaper[i] = stack[-1]
        stack.append(i)
    fuel, previous_mile, last_stop_mile = tank, D(0), D(0)
    purchased, total_cost = D(0), D(0)
    stops = []
    for i, point in enumerate(points):
        fuel -= (point.mile - previous_mile) / mpg
        if fuel < -EPSILON:
            raise PlanningError(f"The station network has an unreachable gap before mile {point.mile:.1f}.")
        fuel = max(D(0), fuel)
        previous_mile = point.mile
        target_distance = min(max_range, distance - point.mile)
        if cheaper[i] is not None:
            target_distance = min(target_distance, points[cheaper[i]].mile - point.mile)
        buy = max(D(0), target_distance / mpg - fuel)
        if buy <= EPSILON:
            continue
        arrival = fuel
        fuel += buy
        if fuel > tank + EPSILON:
            raise AssertionError("Tank capacity exceeded")
        cost = D(money(buy * point.price))
        purchased += buy
        total_cost += cost
        stops.append(
            {
                **point.station,
                "price_per_gallon": str(point.price),
                "route_distance_miles": quantity(point.mile),
                "distance_from_route_miles": round(point.offset_miles, 3),
                "gallons_purchased": quantity(buy),
                "fuel_cost": str(cost),
                "arrival_fuel_gallons": quantity(arrival),
                "remaining_fuel_gallons": quantity(fuel),
                "gallons_consumed_since_previous_stop": quantity((point.mile - last_stop_mile) / mpg),
            }
        )
        last_stop_mile = point.mile
    fuel -= (distance - previous_mile) / mpg
    if fuel < -EPSILON:
        raise PlanningError(
            "Destination is unreachable with the located stations and configured vehicle range."
        )
    return {
        "fuel_stops": stops,
        "fuel_summary": {
            "total_distance_miles": quantity(distance),
            "total_fuel_consumed_gallons": quantity(distance / mpg),
            "total_fuel_purchased_gallons": quantity(purchased),
            "total_fuel_cost": money(total_cost),
            "initial_fuel_gallons": quantity(tank),
            "arrival_fuel_gallons": quantity(max(D(0), fuel)),
            "gallons_consumed_after_last_stop": quantity((distance - last_stop_mile) / mpg),
            "currency": "USD",
            "initial_tank_cost_included": False,
            "detour_fuel_included": False,
        },
    }
