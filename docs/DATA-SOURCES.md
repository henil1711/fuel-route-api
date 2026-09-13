# Data provenance

The original `fuel-prices-for-be-assessment.csv` is supplied by the assignment owner and retained unchanged. It is the sole source of prices and OPIS station IDs. No live prices or invented stations are used. Confirm permission to redistribute this source dataset before publishing a public repository; no new license is asserted over it.

`station-coordinates.csv` contains actual OpenStreetMap fuel POI coordinates linked to these CSV stations. Every row includes a source URL and matching method. The matching report records the OSM snapshot timestamp and unresolved IDs.

OpenStreetMap data is © OpenStreetMap contributors, available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). See [OSM copyright and attribution](https://www.openstreetmap.org/copyright). The derived coordinates remain subject to ODbL; they are provided separately from the assignment price data. Preserve these notices when redistributing them.

Preprocessing first tries exact chain/store references, then a unique chain/city/state match in both datasets. The latter is explicitly marked `approximate identity` and requires review for operational deployment. Multiple POIs farther than 500 metres apart are rejected as ambiguous. City centroids are never substituted for station coordinates.

The initial unrestricted national fuel query timed out. A restricted chain query completed and returned 7,435 actual POIs. The delivered command reproduces that query in **one bulk request**, cached to `fuel_data/osm-us.json`. It performs no individual station searches. The prepared coordinate CSV means this request need not be repeated during setup.

Current coverage: **557 of 6,626 US stations**. Unresolved records remain in the database with null coordinates and all original prices. They are excluded from planning, never silently placed at an invented point. Improve coverage by reviewing OSM matches or supplying a licensed verified `opis_id,latitude,longitude,source` coordinate file to the import command.

Endpoint geocoding uses the [Nominatim Search API](https://nominatim.org/release-docs/latest/api/Search/); routing uses the [OSRM Route API](https://project-osrm.org/docs/v5.24.0/api/#route-service). Both operate on OSM-compatible data.

**Public Nominatim use is limited to a low-traffic, single-host demonstration.** Read the [usage policy](https://operations.osmfoundation.org/policies/nominatim/): identify the application, cache results, serialize requests to at most one per second, do not use autocomplete, and do not use the public service for this station bulk import. This application exposes route planning, not a general geocoding endpoint. Its single-host file lock and 1.1-second request spacing implement the rate limit. The deployer is responsible for provider compliance and should configure a self-hosted or otherwise suitable geocoder for production traffic.

The browser displays [OSM standard tiles](https://operations.osmfoundation.org/policies/tiles/) with visible attribution, normal browser caching, and an origin referrer. It does not prefetch or offer offline tile downloads. Public map services have no application SLA; configure provider URLs appropriate to deployment.
