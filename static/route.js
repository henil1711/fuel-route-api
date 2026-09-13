"use strict";
const map = L.map("map").setView([39.5, -98.35], 4);
L.tileLayer(JSON.parse(document.getElementById("tile-url").textContent), {
  attribution:
    '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 18,
}).addTo(map);
let layer = L.featureGroup().addTo(map);
const form = document.getElementById("planner"),
  status = document.getElementById("status");
function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  form.querySelector("button").disabled = true;
  status.className = "";
  status.textContent = "Finding your route and comparing fuel stops…";
  document.getElementById("summary").hidden = true;
  document.getElementById("stops").hidden = true;
  layer.clearLayers();
  try {
    const response = await fetch("/api/v1/route/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        start: form.elements.start.value,
        finish: form.elements.finish.value,
      }),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(JSON.stringify(data.error?.details || data));
    L.geoJSON(data.route.geometry, {
      style: { color: "#247765", weight: 5 },
    }).addTo(layer);
    for (const [point, label] of [
      [data.start, "Start"],
      [data.finish, "Finish"],
    ]) {
      L.marker([point.latitude, point.longitude])
        .bindPopup(element("span", label + ": " + point.input))
        .addTo(layer);
    }
    const tbody = document.querySelector("tbody");
    tbody.replaceChildren();
    for (const stop of data.fuel_stops) {
      L.circleMarker([stop.latitude, stop.longitude], {
        radius: 9,
        color: "#183c36",
        fillColor: "#d5ed69",
        fillOpacity: 1,
      })
        .bindPopup(
          element(
            "span",
            `${stop.name} · $${Number(stop.price_per_gallon).toFixed(3)}/gal · Buy ${Number(stop.gallons_purchased).toFixed(2)} gal`,
          ),
        )
        .addTo(layer);
      const row = element("tr", "");
      for (const value of [
        `${stop.name} — ${stop.city}, ${stop.state}`,
        Number(stop.route_distance_miles).toFixed(1),
        `$${Number(stop.price_per_gallon).toFixed(3)}`,
        Number(stop.gallons_purchased).toFixed(2),
        `$${stop.fuel_cost}`,
      ])
        row.append(element("td", value));
      tbody.append(row);
    }
    map.fitBounds(layer.getBounds(), { padding: [25, 25] });
    const summary = document.getElementById("summary");
    summary.replaceChildren();
    for (const [value, label] of [
      [`${data.route.distance_miles.toFixed(1)} mi`, "Primary route"],
      [
        `${Number(data.fuel_summary.total_fuel_consumed_gallons).toFixed(1)} gal`,
        "Estimated consumption",
      ],
      [`$${data.fuel_summary.total_fuel_cost}`, "Fuel purchases"],
      [data.fuel_stops.length, "Fuel stops"],
    ]) {
      const metric = element("div", "");
      metric.className = "metric";
      metric.append(element("strong", value), element("span", label));
      summary.append(metric);
    }
    summary.hidden = false;
    document.getElementById("stops").hidden = !data.fuel_stops.length;
    status.textContent = `Compared ${data.metadata.candidate_stations} nearby stations. ${data.metadata.route_cache_hit ? "Route loaded from cache." : "One routing request used."}`;
  } catch (error) {
    status.className = "error";
    status.textContent = error.message;
  } finally {
    form.querySelector("button").disabled = false;
  }
});
