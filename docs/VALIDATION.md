# Completed validation — 13 September 2026

- Installed Django 6.1.1, DRF 3.18.1 and the pinned supporting dependencies in an isolated Python 3.12.14 environment.
- Ran all migrations and created the shared database cache table.
- Imported all 8,151 source records through the management command: 7,531 US rows accepted, 620 Canadian rows excluded, 6,626 US station records, 7,505 distinct observations with duplicate multiplicities retained.
- Populated 557 station coordinate pairs from real OSM POIs and retained source/matching provenance.
- **55 offline tests passed in 0.85 seconds**, including 100 independent exhaustive optimization comparisons inside one test.
- Ruff lint and formatting checks passed. Django system checks passed. Migration drift check reported no changes.
- Started Django at `127.0.0.1:8000` and sent real HTTP POST requests for a short and multi-stop route.
- Repeated live validation for Newark, Chicago and Dallas with real Nominatim/OSRM responses. Every route returned GeoJSON; station IDs, prices and coordinates were checked against imported source records.
- Instrumented real outgoing HTTP requests: one OSRM call on each route cache miss, zero on each repeat, and zero individual station requests. See `live-validation.json` for timings and totals.
- Confirmed the manual 700-mile example: 70 gallons consumed, 50 initially available, 20 bought at $3 = **$60**.
- Visually verified the browser map with actual OSM tiles, the New York–Dallas route, nine stop markers, station table and $324.34 total. Corrected Django's referrer policy so tile requests identify the app's origin as required by OSM.
- Fixed an index invalidation bug found during regression testing: coordinate/price snapshots are now compared directly, so updates in the same clock tick cannot keep a stale index.
- Added `geocode_stations_census`, which generated a six-thousand-six-hundred-twenty-six-row Census batch input. The sandbox blocked outbound connections to the Census host during this turn (`WinError 10013`), so no Census result file was fabricated; run the documented `--submit` command on a network-enabled machine.

## Scope of the evidence

These checks establish the implemented behavior and the recorded examples. They do not certify all possible US routes, station road access, live prices, full coordinate coverage, or public provider availability. Station access detours and initial tank costs are excluded. City-based POI identity matches are marked approximate. Public production deployment still requires the environment, HTTPS/static serving and provider configuration described in the README.

GitHub Actions is provided, but no remote repository was created or CI run claimed. No external deployment was performed.
