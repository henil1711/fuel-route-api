from decimal import Decimal as D
import random

import pytest
from routes.exceptions import PlanningError
from routes.services.fuel_optimizer import Candidate, optimize


def candidate(opis, mile, price):
    return Candidate({"opis_id": opis, "name": f"Station {opis}"}, D(str(mile)), 0, D(str(price)))


@pytest.mark.parametrize("distance", [0, 1, 499.999999, 500])
def test_no_stop_needed(distance):
    result = optimize(D(str(distance)), [])
    assert result["fuel_stops"] == []
    assert result["fuel_summary"]["total_fuel_cost"] == "0.00"


def test_cheaper_reachable_station_and_manual_cost():
    # Arrive at mile 400 with 10 gal, buy 20 at $3, arrive at mile 700 empty.
    plan = optimize(D(700), [candidate(1, 200, 4), candidate(2, 400, 3)])
    assert [p["opis_id"] for p in plan["fuel_stops"]] == [2]
    assert plan["fuel_stops"][0]["gallons_purchased"] == "20.000000"
    assert plan["fuel_summary"]["total_fuel_cost"] == "60.00"
    assert plan["fuel_summary"]["arrival_fuel_gallons"] == "0.000000"


def test_unreachable_cheap_station_requires_expensive_bridge():
    result = optimize(D(900), [candidate(1, 400, 5), candidate(2, 650, 2)])
    assert [s["opis_id"] for s in result["fuel_stops"]] == [1, 2]
    assert result["fuel_stops"][0]["gallons_purchased"] == "15.000000"
    assert result["fuel_summary"]["total_fuel_cost"] == "125.00"


def test_multiple_stops_tank_and_conservation():
    plan = optimize(D(1700), [candidate(i, i * 400, 4 - i / 10) for i in range(1, 5)])
    assert len(plan["fuel_stops"]) >= 3
    summary = plan["fuel_summary"]
    assert D(summary["initial_fuel_gallons"]) + D(summary["total_fuel_purchased_gallons"]) == D(
        summary["total_fuel_consumed_gallons"]
    ) + D(summary["arrival_fuel_gallons"])
    for stop in plan["fuel_stops"]:
        assert 0 <= D(stop["arrival_fuel_gallons"]) <= D(stop["remaining_fuel_gallons"]) <= 50


@pytest.mark.parametrize(
    "distance,points",
    [(501, []), (1200, [candidate(1, 400, 3)]), (1300, [candidate(1, 400, 3), candidate(2, 950, 2)])],
)
def test_infeasible_network(distance, points):
    with pytest.raises(PlanningError):
        optimize(D(distance), points)


def test_same_position_and_equal_price_are_deterministic():
    points = [candidate(2, 400, 3), candidate(1, 400, 3), candidate(3, 700, 3)]
    assert optimize(D(900), points) == optimize(D(900), list(reversed(points)))
    assert optimize(D(900), points)["fuel_summary"]["total_fuel_cost"] == "120.00"


@pytest.mark.parametrize(
    "distance,range_,mpg",
    [(D(-1), D(500), D(10)), (D(1), D(0), D(10)), (D(1), D(500), D(0)), (D("NaN"), D(500), D(10))],
)
def test_invalid_parameters(distance, range_, mpg):
    with pytest.raises(ValueError):
        optimize(distance, [], range_, mpg)


def test_random_plans_match_independent_exhaustive_dynamic_program():
    rng = random.Random(90210)
    for _ in range(100):
        # Integer consumption instances have an integer optimum. Exhaust every
        # possible purchase amount; no next-cheaper logic is shared with production.
        units = sorted(rng.sample(range(1, 190), 20))
        prices = [rng.randint(250, 600) for _ in units]
        states, previous = {50: 0}, 0
        for position, price in zip(units, prices, strict=True):
            arriving = {
                fuel - (position - previous): cost
                for fuel, cost in states.items()
                if fuel >= position - previous
            }
            states = {}
            for fuel, cost in arriving.items():
                for bought in range(51 - fuel):
                    total = cost + bought * price
                    states[fuel + bought] = min(states.get(fuel + bought, float("inf")), total)
            previous = position
        feasible = [cost for fuel, cost in states.items() if fuel >= 190 - previous]
        points = [
            candidate(i, unit * 10, D(price) / 100)
            for i, (unit, price) in enumerate(zip(units, prices, strict=True))
        ]
        if not feasible:
            with pytest.raises(PlanningError):
                optimize(D(1900), points)
        else:
            actual = optimize(D(1900), points)
            exact = sum(D(s["gallons_purchased"]) * D(s["price_per_gallon"]) for s in actual["fuel_stops"])
            assert exact == D(min(feasible)) / 100
