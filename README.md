# Fuel Route API

A Django REST backend that finds a US driving route, matches locally stored fuel stations to its geometry, and computes how much fuel to buy at each stop to minimize purchase cost. Includes a Leaflet map, the actual assignment CSV, prepared station coordinates, Postman requests, tests, and recorded live API responses.

**Implemented and tested with Python 3.12.14, Django 6.1.1 and Django REST Framework 3.18.1.** Django 6.1.1 was the [latest stable release](https://www.djangoproject.com/download/) on 13 September 2026.

The optimizer is optimal for the **selected route, located candidates, continuous fuel quantities, and excluded detours**. It is an assessment implementation with explicit approximations, not a road-access or live-price guarantee. Current coordinate coverage is **557 / 6,626 US stations**. The code and preprocessing are complete; extending verified coordinate coverage is the main remaining data limitation.

## Quick start

Requires Python 3.12+ and internet access for dependency installation. In the project directory:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createcachetable
.venv\Scripts\python.exe manage.py import_fuel_prices fuel_data/fuel-prices-for-be-assessment.csv --report fuel_data/dataset-report.json
.venv\Scripts\python.exe manage.py import_station_coordinates fuel_data/station-coordinates.csv
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

On macOS/Linux, use `python3 -m venv .venv`, `cp .env.example .env`, and replace `.venv\Scripts\python.exe` with `.venv/bin/python`. No station-geocoding calls are required to start: the prepared coordinate CSV is included.

Open [the map demo](http://127.0.0.1:8000/route/). Try New York, NY → Chicago, IL, then New York, NY → Dallas, TX. A full tank is provided at departure.

## Architecture

```text
config/                         Environment settings, URLs, ASGI/WSGI
routes/models.py                Stations and retained price observations
routes/serializers.py            Strict bounded text input validation
routes/views.py                  Thin API/map/health views
routes/services/
  geocoding.py                  Cached, rate-limited endpoint lookup
  routing.py                    Cached OSRM request + response validation
  station_matcher.py             Local STRtree + projected route matching
  fuel_optimizer.py              Pure deterministic Decimal fuel planner
  planner.py                    Service orchestration and response assembly
  importer.py                   CSV validation, inspection, snapshot import
  cache.py                      Deterministic keys and single-host request locks
routes/management/commands/      Import prices, batch locate, import coordinates
routes/tests/                   Offline tests and independent optimizer oracle
templates/, static/             Small Leaflet browser demo
fuel_data/                      Original CSV, reports, sourced coordinates
docs/                           Real responses, validation results, provenance
postman/                        Collection using {{base_url}}
scripts/validate_live.py         Explicit real-provider validation
.github/workflows/tests.yml      CI checks
```

Django provides migrations, database transactions, configuration, caching, and established HTTP protections. DRF adds request validation, structured errors, JSON responses, and anonymous throttling. SQLite is adequate for this dataset and a single application host. CSV parsing uses Python's standard library rather than adding pandas solely for 8,151 rows. NumPy, Shapely and pyproj handle the spatial work.

OSRM was chosen for its no-key public demonstration endpoint, full GeoJSON road geometry, distance/duration output, and self-hosting option. Nominatim supplies OSM-compatible city/state lookup without a paid key. Public endpoints are suitable for a modest demonstration, not an availability promise. See [provider policies and attribution](docs/DATA-SOURCES.md) before deployment.

## What the supplied CSV actually contains

The unmodified file is `fuel_data/fuel-prices-for-be-assessment.csv`.

| Inspection | Result |
|---|---:|
| Source rows | 8,151 |
| Unique OPIS IDs, all countries | 6,738 |
| IDs appearing multiple times, all countries | 678 |
| Repeated normalized address/city/state groups | 937 |
| Missing values in the seven required columns | 0 |
| Malformed rows / invalid prices | 0 / 0 |
| Observed price range | 2.68733333–6.399 |
| US rows accepted | 7,531 |
| Canadian rows excluded from planning | 620 |
| US stations | 6,626 |
| Distinct US observations | 7,505 |
| Exact duplicate US rows | 26 |
| US station IDs with multiple prices | 487 |
| Latitude/longitude columns | None |

The exact columns are `OPIS Truckstop ID`, `Truckstop Name`, `Address`, `City`, `State`, `Rack ID`, `Retail Price`. IDs/rack IDs parse as integers, prices as Decimal with up to eight fractional digits, and the other fields as text. Canadian values include AB, BC, MB, NB, NS, ON, QC, SK and YT. Complete per-state counts and inspection results are in [dataset-report.json](fuel_data/dataset-report.json).

### Import and duplicate policy

The import is an atomic **complete snapshot replacement**, not an append operation. It validates headers and fields, normalizes whitespace and state codes, reports rejected rows, and performs batched writes. A completely invalid or empty snapshot leaves existing data untouched. Stations absent from a valid new snapshot are removed; run imports as maintenance work, not concurrently with traffic.

One `FuelStation` exists per OPIS ID. Each distinct normalized source row is retained in `FuelPrice`, including rack ID, eight-decimal price, original field values after normalization, and duplicate occurrence count. The original file remains available unchanged. Different OPIS IDs at the same address are retained: the dataset does not establish that they are the same business.

The optimizer uses the **minimum observed price per station**. The file has no timestamps or fuel grades, so neither “latest” nor “correct grade” can be inferred. The chosen rule is explicit and reproducible, but optimistic. Source observations are not silently discarded. Reimporting the same file is idempotent; replacing it refreshes prices rather than retaining stale minima. Coordinates survive price-only changes and are invalidated when station identity/address metadata changes.

### Locating stations without thousands of calls

Prepared real POI coordinates are supplied separately in `station-coordinates.csv`, with an OSM URL and match method for every row. Rebuild them when needed:

```text
python manage.py locate_stations --download
```

This makes one explicit Overpass request for a national extract of relevant fuel brands and caches the JSON locally. Reusing `--osm-file path/to/extract.json` performs no network calls. Matching first uses exact chain/store references; the fallback requires a unique chain/city/state combination in both datasets. Conflicting store references, conflicting state tags, and spatially ambiguous matches are rejected. The fallback is marked as approximate identity. It uses actual fuel POIs, never city-centroid coordinates.

The delivered snapshot locates 557 stations. The remaining 6,069 have null coordinates and do not participate. For broader coverage, review unmatched stations against licensed POI data and import a verified CSV:

The project also includes `geocode_stations_census`, which submits the 6,626 unique US stations as one Census batch (under its 10,000-row limit):

```text
python manage.py geocode_stations_census
python manage.py geocode_stations_census --submit
```

It writes the reviewable input, raw response, matched coordinate CSV, and status report. Census `No_Match` results remain unresolved rather than receiving guessed coordinates. Review the report before importing. This is preprocessing only; normal API requests never call Census.

```text
opis_id,latitude,longitude,source
```

```text
python manage.py import_station_coordinates path/to/verified-coordinates.csv
```

This command is atomic, validates finite coordinate pairs, requires known OPIS IDs and source provenance, and rejects duplicate IDs. Its input contract is trusted, verified US station coordinates; it cannot establish station identity from latitude/longitude alone. **Normal API requests never geocode stations.** The public Nominatim service is not used for bulk station preprocessing.

## Route matching and fuel optimization

An in-process spatial index holds the roughly 8,000-or-fewer station points. One local database query reads an immutable snapshot of located stations; an LRU cache reuses the index only when that snapshot is equal. This avoids stale prices or coordinates, including updates within the same clock tick, without rebuilding the index on every request. Shapely's STRtree restricts the search to a padded projected route corridor, then finds the nearest route segment. pyproj checks the actual station offset with WGS84 ellipsoidal distance. Segment fractions and cumulative geodesic lengths are scaled to OSRM's reported driving mileage. The default corridor is five miles, configurable.

The projection uses EPSG:2163 for US coverage. Offsets and along-route positions are estimates: unusual loops, long sparse segments, polar routes and antimeridian crossings require a more specialized implementation. The standard continental-US examples use dense OSRM geometry.

The independent optimizer sorts candidates by cumulative route mileage, price and OPIS ID. A monotonic stack precomputes the next strictly cheaper station. At each candidate it:

1. Deducts fuel consumed since the previous route point and rejects unreachable gaps.
2. If a cheaper station is within tank range, targets just enough fuel to reach it.
3. Otherwise targets a full tank, capped by fuel needed to reach the destination.
4. Buys only the shortfall relative to fuel already aboard.
5. Records a stop only when a positive purchase occurs.

This is the standard exchange argument: buying extra before a reachable cheaper station cannot reduce cost; with no cheaper station in range, buying usable fuel at the current price cannot worsen cost. Initial free fuel is preserved. Sorting takes O(n log n); the next-cheaper search and simulation take O(n). The tests independently exhaust all integer fuel purchase choices on 100 randomized integral-distance instances, rather than reimplementing the same greedy rule.

The vehicle starts with **50 gallons**, travels **10 MPG**, and has **500 miles of range**. A route up to 500 miles can cost $0 in *new purchases*. This does not mean the trip consumes no fuel. Detour fuel, stop time, road access, reserve margins and the sunk cost of the initial tank are excluded. No fixed stopping penalty is charged, so small top-ups can be economically optimal. The plan is optimal for this route model, not across alternative roads or all unlocated stations.

Money uses Decimal, never binary floating-point multiplication. Provider mileage is converted to Decimal before fuel accounting. Individual stop totals are rounded half-up to cents, and the displayed total is the sum of those cents. Fuel quantities are serialized to six decimals; prices to their stored precision. Tiny display-rounding differences can occur when independently summing displayed quantities. Optimization targets unrounded fuel cost, not sub-cent receipt-rounding opportunities.

## API

`POST /api/v1/route/` — JSON, no authentication required for this assessment.

```json
{"start": "New York, NY", "finish": "Chicago, IL"}
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/route/ \
  -H 'Content-Type: application/json' \
  -d '{"start":"New York, NY","finish":"Chicago, IL"}'
```

Both fields must be nonblank strings of 2–200 characters. The geocoder's returned country code must be US; the input is not blindly assumed domestic. Coordinates and arbitrary external URLs are not accepted as a separate input format. A US city/state is recommended. Only endpoints are checked: an OSRM route between US endpoints may cross another country.

The response includes start/finish coordinates, full `route.geometry` as a GeoJSON LineString in **longitude, latitude** order, route mileage/duration, vehicle settings, fuel stops, fuel summary, coverage and assumptions. Money and gallon quantities are decimal strings. `remaining_fuel_gallons` at a stop means **after purchasing**, while `arrival_fuel_gallons` means before purchasing.

The recorded New York–Chicago response has 12,624 geometry points, 790.565721 miles, two stops, 29.056572 gallons purchased, and $99.57 cost. This excerpt shows its summary; [the complete response](docs/live-chicago-response.json) contains the actual geometry and station details:

```json
{
  "fuel_summary": {
    "total_distance_miles": "790.565721",
    "total_fuel_consumed_gallons": "79.056572",
    "total_fuel_purchased_gallons": "29.056572",
    "total_fuel_cost": "99.57",
    "initial_fuel_gallons": "50.000000",
    "arrival_fuel_gallons": "0.000000",
    "currency": "USD",
    "initial_tank_cost_included": false,
    "detour_fuel_included": false
  }
}
```

`GET /route/` serves the map and stop table; `GET /health/` is a simple process-health endpoint.

| HTTP status | Meaning |
|---|---|
| 400 | Invalid/missing input, unresolvable location, or non-US location |
| 405 / 415 | Unsupported method / content type |
| 422 | No driving route, or no feasible fuel plan in the located network |
| 429 | Anonymous request rate limit exceeded |
| 503 | Provider timeout, failure, malformed result or lock contention |

Errors have `{"error":{"code":"...","details":{...}}}`. Internal provider exceptions are logged by type and not exposed in JSON. Requests use fixed configured providers, timeouts, and no automatic external retries.

## How we keep routing API calls to one per uncached route

Geocode only the two endpoint strings (both cached), then call OSRM **once** with `overview=full&geometries=geojson&steps=false&alternatives=false`. All station filtering, route projection and optimization occur locally against that result. No station-to-station routes, route matrix, or waypoint rerouting is requested. A deterministic SHA-256 cache key includes the configured OSRM base URL and start/finish coordinates rounded to six decimals; those same coordinates are sent to OSRM. Direction is preserved.

Route cache TTL defaults to one day; geocoding to 30 days. Database caching shares results between processes on one host. File locks prevent simultaneous identical route misses from duplicating requests. Geocoding is globally serialized on that host with at least 1.1 seconds between starts. Public Nominatim requires one application machine; a multi-host deployment needs a shared rate limiter and suitable provider. Lock waits are bounded. The station index is local; fuel plans are recomputed against current local prices on every request, avoiding stale full-response caches.

Measured real requests with endpoint geocodes already cached:

| From New York to | Miles | Stops | Purchase cost | Uncached / cached seconds | Actual outgoing calls |
|---|---:|---:|---:|---:|---|
| Newark | 10.31 | 0 | $0.00 | 0.602 / 0.011 | 1 / 0 |
| Chicago | 790.57 | 2 | $99.57 | 1.186 / 0.075 | 1 / 0 |
| Dallas | 1,548.50 | 9 | $324.34 | 1.075 / 0.126 | 1 / 0 |

These are observations on the implementation machine, not guaranteed service latencies. The two uncached endpoint lookups add provider time and rate-limit spacing. [live-validation.json](docs/live-validation.json) records actual HTTP call counts observed around real provider requests, rather than merely trusting response metadata.

## Configuration and deployment

Copy `.env.example` for local development. Provider URLs are settings/environment values, not embedded in service code.

| Variable | Default / role |
|---|---|
| `DJANGO_DEBUG` | False unless enabled by the demo `.env` |
| `DJANGO_SECRET_KEY` | Required when debug is false |
| `DJANGO_ALLOWED_HOSTS` | Explicit comma-separated hosts |
| `OSRM_BASE_URL` | Public OSRM demo; replace for production |
| `GEOCODING_BASE_URL` | Nominatim-compatible provider |
| `GEOCODING_USER_AGENT` | Application identification; customize for your deployment |
| `OVERPASS_BASE_URL` | Bulk preprocessing endpoint |
| `TILE_URL` | OSM-compatible raster tile URL template |
| `CACHE_TIMEOUT` | Route TTL, 86400 seconds |
| `GEOCODING_CACHE_TIMEOUT` | Endpoint TTL, 2592000 seconds |
| `MAX_STATION_ROUTE_DISTANCE_MILES` | 5 |
| `VEHICLE_MAX_RANGE_MILES` / `VEHICLE_MPG` | 500 / 10 |
| `SECURE_SSL_REDIRECT` / `SECURE_HSTS_SECONDS` | Configure for HTTPS deployment |

For deployment use `DJANGO_DEBUG=false`, a generated secret, explicit hosts, HTTPS, and a WSGI server such as `waitress-serve --listen=127.0.0.1:8000 config.wsgi:application` behind a reverse proxy. Run `python manage.py collectstatic --noinput` and serve `staticfiles/` at `/static/` from that proxy; Waitress does not serve static files. Run `python manage.py check --deploy` against deployment settings. No CORS policy is needed for the same-origin map. The endpoint has an 8-KiB request-data limit and 30/minute anonymous throttling; enforce body, connection and rate limits at the proxy for public exposure. SQLite and file locks deliberately target one host. A multi-host deployment should use PostgreSQL, shared cache/locks and suitable service quotas.

## Tests and validation

```text
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
```

The offline suite covers CSV parsing and duplicate retention, malformed input, foreign records, atomic coordinate imports, cache invalidation, tank capacity, cheap/unreachable stations, multiple stops, short/exact-range routes, infeasible gaps, independent cost optimality, route matching, API schemas, mocked geocoding/OSRM, provider failures and caching. CI runs these without live APIs.

Final local result: **55 tests passed**, including the randomized independent oracle, concurrent cache-miss protection and database coordinate constraints. Ruff lint/format checks, Django system checks and migration drift checks passed. The browser map was visually checked with real OSM tiles, the Dallas route and its nine fuel markers.

Manual arithmetic check: on a 700-mile route starting with 50 gallons, pass a $4 station at mile 200 and buy 20 gallons at a $3 station at mile 400. Consumption is 70 gallons; purchases cost **20 × $3 = $60**, and arrival fuel is zero. This is also a regression test.

To deliberately repeat the live validation after setup:

```text
python scripts/validate_live.py
```

It checks short, Chicago and multi-stop Dallas routes; captures full real geometry; verifies every selected OPIS ID and price against imported source observations; checks fuel limits and stop-cost sums; then repeats each route and asserts zero additional outgoing HTTP calls. It writes reports under `docs/`. Unlike the test suite, this script requires network access and uses the public providers.

## Postman and five-minute demonstration

Import `postman/Fuel-Route.postman_collection.json`. The collection includes Newark, Chicago, Dallas and a non-US validation example. `base_url` defaults to `http://127.0.0.1:8000`. Successful requests assert the geometry and summary schema.

| Time | Demonstration |
|---|---|
| 0:00–0:30 | Explain US route planning, 500-mile range and purchase-cost objective |
| 0:30–1:15 | Show the small Django architecture and actual dataset report |
| 1:15–2:30 | Send Chicago, then Dallas in Postman; repeat to show cache hit |
| 2:30–3:30 | Explain geometry, station provenance, quantities and total cost |
| 3:30–4:15 | Open `/route/`, plot Dallas, inspect markers and nine-stop table |
| 4:15–5:00 | Show routing, matcher, optimizer, independent tests and one-call evidence |

Be explicit during the demonstration: prices are historical observations without grade/date metadata, coverage is partial, some POI identities are approximate, and station access detours are excluded. These limitations are also returned with every successful API response.
