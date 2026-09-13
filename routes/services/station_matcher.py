"""Local spatial index; no network requests or CSV parsing."""

from functools import lru_cache
from decimal import Decimal

import numpy as np
import shapely
from pyproj import Geod, Transformer
from shapely import LineString, Point, STRtree

from routes.models import FuelStation
from .fuel_optimizer import Candidate

GEOD = Geod(ellps="WGS84")
FORWARD = Transformer.from_crs("EPSG:4326", "EPSG:2163", always_xy=True)
INVERSE = Transformer.from_crs("EPSG:2163", "EPSG:4326", always_xy=True)
METERS_PER_MILE = 1609.344
STATION_FIELDS = (
    "opis_id",
    "name",
    "city",
    "state",
    "address",
    "latitude",
    "longitude",
    "retail_price",
    "coordinate_source",
)


@lru_cache(maxsize=2)
def _station_index(snapshot: tuple):
    rows = [dict(zip(STATION_FIELDS, row, strict=True)) for row in snapshot]
    if not rows:
        return rows, [], None
    x, y = FORWARD.transform([r["longitude"] for r in rows], [r["latitude"] for r in rows])
    points = shapely.points(x, y)
    return rows, points, STRtree(points)


def match_stations(route: dict, max_offset_miles: float) -> tuple[list[Candidate], int]:
    # One small local query gives a consistent immutable snapshot. Tuple equality
    # invalidates on actual changes, including updates within the same clock tick.
    snapshot = tuple(
        FuelStation.objects.filter(latitude__isnull=False, longitude__isnull=False)
        .order_by("opis_id")
        .values_list(*STATION_FIELDS)
    )
    rows, station_points, tree = _station_index(snapshot)
    if tree is None or route["distance_miles"] == 0:
        return [], len(rows)
    coords = np.asarray(route["geometry"]["coordinates"], dtype=float)
    x, y = FORWARD.transform(coords[:, 0], coords[:, 1])
    xy = np.column_stack([x, y])
    segment_lengths = GEOD.inv(coords[:-1, 0], coords[:-1, 1], coords[1:, 0], coords[1:, 1])[2]
    cumulative = np.concatenate([[0], np.cumsum(segment_lengths)])
    if cumulative[-1] <= 0:
        return [], len(rows)
    line = LineString(xy)
    # Padded projected corridor, followed by an ellipsoidal distance check.
    indices = tree.query(line, predicate="dwithin", distance=max_offset_miles * METERS_PER_MILE * 1.3 + 1)
    segments = [LineString([a, b]) for a, b in zip(xy[:-1], xy[1:], strict=True)]
    segment_tree = STRtree(segments)
    result = []
    for index in indices:
        point = station_points[index]
        seg_index = int(segment_tree.nearest(point))
        segment = segments[seg_index]
        fraction = segment.project(point, normalized=True) if segment.length else 0
        nearest: Point = segment.interpolate(fraction, normalized=True)
        lon, lat = INVERSE.transform(nearest.x, nearest.y)
        row = rows[index]
        offset = GEOD.inv(row["longitude"], row["latitude"], lon, lat)[2] / METERS_PER_MILE
        if offset > max_offset_miles:
            continue
        along = cumulative[seg_index] + fraction * segment_lengths[seg_index]
        mile = along / cumulative[-1] * route["distance_miles"]
        station = {k: v for k, v in row.items() if k != "retail_price"}
        result.append(Candidate(station, Decimal(str(mile)), offset, row["retail_price"]))
    return result, len(rows)
