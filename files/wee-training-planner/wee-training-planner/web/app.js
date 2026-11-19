"use strict";

// Normally the page is served by the API (http://localhost:8000), so a relative path works.
// If index.html is opened straight from disk, fall back to the local API address.
const ORIGIN = location.protocol === "file:" ? "http://localhost:8000" : "";
const API = ORIGIN + "/api";

const DCOLOR = { Salima: "#1B8A8F", Mangochi: "#4C63B6", Balaka: "#B9772E" };
const FALLBACK_COLOR = "#5A6F75";

const ICON = {
  school: '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5"/>',
  people: '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6"/><circle cx="17" cy="9" r="2.5"/><path d="M17 14c2.8 0 5 2 5 5"/>',
  worship: '<path d="M12 3v6M9.5 6h5"/><path d="M5 21V13l7-4 7 4v8z"/>',
  market: '<path d="M3 9l2-5h14l2 5"/><path d="M4 9v11h16V9"/><path d="M9 20v-6h6v6"/>',
  health: '<path d="M12 5v14M5 12h14"/>',
  office: '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 8h2M13 8h2M9 12h2M13 12h2M10 21v-4h4v4"/>',
  hall: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  pin: '<path d="M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11z"/><circle cx="12" cy="10" r="2"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
  warn: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
};
const TYPES = [
  { id: "primary_school", label: "Primary schools", one: "Primary school", color: "#2F6FD0", icon: "school" },
  { id: "secondary_school", label: "Secondary schools", one: "Secondary school", color: "#4A55B8", icon: "school" },
  { id: "school", label: "Other schools", one: "School", color: "#3C7DC4", icon: "school" },
  { id: "cooperative", label: "Cooperatives", one: "Cooperative", color: "#1B8A5A", icon: "people" },
  { id: "community_hall", label: "Halls", one: "Community hall", color: "#7A4FA3", icon: "hall" },
  { id: "worship", label: "Churches and mosques", one: "Church or mosque", color: "#9A6B2F", icon: "worship" },
  { id: "market", label: "Markets", one: "Market", color: "#C2641C", icon: "market" },
  { id: "health_centre", label: "Health centres", one: "Health centre", color: "#C2342C", icon: "health" },
  { id: "extension_office", label: "Extension offices", one: "Extension office", color: "#0D3B45", icon: "office" },
  { id: "other", label: "Other places", one: "Other venue", color: "#5A6F75", icon: "pin" },
];
const TYPE = Object.fromEntries(TYPES.map((t) => [t.id, t]));
const KIND = {
  optimal: { one: "Optimal point, not an existing venue", color: "#0D3B45", icon: "target" },
  fairest: { one: "Centre point, not an existing venue", color: "#0D3B45", icon: "target" },
  clicked: { one: "Point you picked", color: "#B83280", icon: "pin" },
};
const BANDS = [
  { label: "Up to 2 km", color: "#1B9AAA" },
  { label: "2 to 5 km", color: "#6DBE9C" },
  { label: "5 to 10 km", color: "#F2C14E" },
  { label: "10 to 20 km", color: "#F08A4B" },
  { label: "Over 20 km", color: "#C2185B" },
];
const MAX_LINES = 450;

const state = {
  districts: [], district: null, farmers: [], flagged: [], venues: [], epas: [], hasOutline: false,
  types: new Set(TYPES.map((t) => t.id)), epaSel: new Set(), showFlagged: false,
  plan: null, selected: null, cohort: null, mode: null, markers: new Map(), epaLayers: new Map(),
  triedBoundary: new Set(), loadToken: 0, sweep: 0, pendingVenue: null, importDone: null,
};

// ------------------------------------------------------------ helpers
const $ = (id) => document.getElementById(id);
const nf = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const mwk = (v) => "MWK " + nf.format(Math.round(v));
const km1 = (v) => v.toFixed(1) + " km";
const plural = (n, one, many) => `${nf.format(n)} ${n === 1 ? one : many}`;
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const colorOf = (district) => DCOLOR[district] || FALLBACK_COLOR;

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c != null) node.append(c);
  return node;
}
function icon(name) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", fill: "none", "stroke-width": "2",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) s.setAttribute(k, v);
  s.innerHTML = ICON[name];
  return s;
}
const iconHTML = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name]}</svg>`;

function detailText(d) {
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  return typeof d === "string" ? d : JSON.stringify(d);
}
async function api(path, options) {
  let res;
  try { res = await fetch(API + path, options); }
  catch { throw new Error("Cannot reach the planner's server. Open http://localhost:8000 and check that Docker is running."); }
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = detailText((await res.json()).detail ?? msg); } catch { /* keep statusText */ }
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

let toastTimer;
function toast(msg, kind = "", ms) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast show " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), ms || (kind === "error" ? 9000 : 5500));
}
const showError = (e) => { console.error(e); toast(e.message, "error"); };

// ------------------------------------------------------------ map
const map = L.map("map", { preferCanvas: true, zoomControl: false }).setView([-13.9, 34.6], 8);
L.control.zoom({ position: "bottomright" }).addTo(map);
const baseMaps = {
  "Clean grey": L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 16, attribution: "Tiles &copy; Esri" }),
  "Terrain": L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 18, attribution: "Tiles &copy; Esri" }),
  "Satellite": L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 18, attribution: "Tiles &copy; Esri, Maxar, Earthstar Geographics" }),
  "OpenStreetMap": L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 18, attribution: "&copy; OpenStreetMap contributors" }),
};
baseMaps["Clean grey"].addTo(map);

const boundaryLayer = L.layerGroup().addTo(map);
const epaLayer = L.layerGroup().addTo(map);
const farmerLayer = L.layerGroup().addTo(map);
const flaggedLayer = L.layerGroup();
const lineLayer = L.layerGroup().addTo(map);
const venueLayer = L.layerGroup().addTo(map);
const siteLayer = L.layerGroup().addTo(map);
L.control.layers(baseMaps, {
  "District outline": boundaryLayer, "EPA areas": epaLayer, "Farmers": farmerLayer,
  "Flagged locations": flaggedLayer, "Venues": venueLayer,
}, { position: "topright" }).addTo(map);
map.on("overlayadd overlayremove", (e) => {
  if (e.layer === flaggedLayer) {
    state.showFlagged = map.hasLayer(flaggedLayer);
    const box = $("show-flagged");
    if (box) box.checked = state.showFlagged;
  }
});

// ------------------------------------------------------------ panes and modes
function showPane(name) {
  for (const b of document.querySelectorAll(".step")) b.setAttribute("aria-selected", String(b.dataset.pane === name));
  for (const p of ["data", "plan", "results"]) $("pane-" + p).hidden = p !== name;
  document.querySelector(".panes").scrollTop = 0;
}
for (const b of document.querySelectorAll(".step")) b.addEventListener("click", () => showPane(b.dataset.pane));

function setMode(mode) {
  state.mode = state.mode === mode ? null : mode;
  $("btn-test").setAttribute("aria-pressed", String(state.mode === "test"));
  const add = $("btn-addvenue");
  if (add) add.setAttribute("aria-pressed", String(state.mode === "addvenue"));
  $("map").classList.toggle("pick", state.mode !== null);
  if (state.mode === "test") toast("Click anywhere on the map to test that point as the meeting place.");
  if (state.mode === "addvenue") toast("Click the map where the venue is.");
}

// ------------------------------------------------------------ districts and data
async function refreshDistricts(preferred) {
  state.districts = await api("/districts");
  const withData = state.districts.find((d) => d.farmers > 0);
  $("welcome").hidden = Boolean(withData);
  const names = state.districts.map((d) => d.name);
  const target = names.includes(preferred) ? preferred
    : names.includes(state.district) ? state.district : (withData || state.districts[0] || {}).name || null;
  await selectDistrict(target);
}

function renderTabs() {
  const nav = $("district-tabs");
  nav.replaceChildren();
  for (const d of state.districts) {
    nav.append(el("button", {
      type: "button", role: "tab", class: "dtab", "aria-selected": String(d.name === state.district),
      style: `--c:${colorOf(d.name)}`, onclick: () => selectDistrict(d.name),
    }, [el("i", { class: "dot" }), el("span", { text: d.name }), el("small", { text: d.farmers ? nf.format(d.mapped) : "no data" })]));
  }
}

async function selectDistrict(name) {
  showPane("data");
  setMode(null); state.mode = null;
  await loadDistrict(name);
}

function clearMap() {
  for (const l of [boundaryLayer, epaLayer, farmerLayer, flaggedLayer, lineLayer, venueLayer, siteLayer]) l.clearLayers();
  state.markers.clear(); state.epaLayers.clear();
}

function clearResults() {
  state.plan = null; state.selected = null; state.cohort = null; state.sweep++;
  $("results-body").replaceChildren(); $("results-body").hidden = true; $("results-empty").hidden = false;
  lineLayer.clearLayers(); siteLayer.clearLayers();
  updateLegend();
}

async function loadDistrict(name) {
  const token = ++state.loadToken;
  state.district = name;
  clearResults(); clearMap(); renderTabs();
  state.farmers = []; state.flagged = []; state.venues = []; state.epas = [];
  state.epaSel.clear(); state.types = new Set(TYPES.map((t) => t.id));
  if (!name) { renderData(); syncPlan(); renderKpis(); return; }
  const q = encodeURIComponent(name);
  let boundary;
  try {
    const [pts, venues, epas, b] = await Promise.all([
      api(`/farmers?district=${q}`), api(`/venues?district=${q}`), api(`/epas?district=${q}`), api(`/boundaries?district=${q}`)]);
    if (token !== state.loadToken) return;
    state.farmers = pts.filter((p) => p.quality === "ok");
    state.flagged = pts.filter((p) => p.quality === "outlier");
    state.venues = venues; state.epas = epas; boundary = b;
  } catch (e) { showError(e); return; }
  drawBoundary(boundary); drawEpas(); drawFarmers(); drawVenues();
  renderData(); syncPlan(); renderKpis(); updateLegend(); fitDistrict(); loadScenarios();
  if (!boundary.features.some((f) => f.properties.level === "district") && !state.triedBoundary.has(name)) {
    state.triedBoundary.add(name);
    fetchBoundary(name, token);
  }
}

async function fetchBoundary(name, token) {
  toast(`Fetching the ${name} district outline from OpenStreetMap\u2026`);
  try {
    await post("/boundaries/fetch", { district: name });
    if (token !== state.loadToken) return;
    drawBoundary(await api(`/boundaries?district=${encodeURIComponent(name)}`));
    state.districts = await api("/districts");
    renderTabs(); renderData(); fitDistrict();
    toast(`${name} district outline loaded.`, "ok", 3500);
  } catch (e) {
    toast(`The district outline could not be loaded: ${e.message} You can upload one from Data, Import a list or boundaries.`, "warn", 11000);
  }
}

function drawBoundary(fc) {
  boundaryLayer.clearLayers();
  const c = colorOf(state.district);
  for (const f of fc.features) {
    if (f.properties.level !== "district") continue;
    L.geoJSON(f, { style: { color: c, weight: 3, fillColor: c, fillOpacity: 0.04, interactive: false }, interactive: false }).addTo(boundaryLayer);
  }
  state.hasOutline = boundaryLayer.getLayers().length > 0;
}

function drawEpas() {
  epaLayer.clearLayers(); state.epaLayers.clear();
  const c = colorOf(state.district);
  for (const e of state.epas) {
    if (!e.outline) continue;
    const g = L.geoJSON(e.outline, { style: { color: c, weight: 1.8, dashArray: "7 5", fillColor: c, fillOpacity: 0.07 }, interactive: false }).addTo(epaLayer);
    state.epaLayers.set(e.epa, g);
    if (e.lat != null) {
      L.marker([e.lat, e.lon], { interactive: false, keyboard: false,
        icon: L.divIcon({ className: "", iconSize: [0, 0], html: `<span class="epa-label" style="--c:${c}">${e.epa} EPA</span>` }) }).addTo(epaLayer);
    }
  }
}

function drawFarmers() {
  const c = colorOf(state.district);
  for (const f of state.farmers) {
    const m = L.circleMarker([f.lat, f.lon], { radius: 3.6, weight: 0, fillColor: c, fillOpacity: 0.7 });
    m.bindTooltip(`${f.village || "Village not recorded"}${f.ward ? ", " + f.ward : ""}, ${f.epa} EPA`);
    m.addTo(farmerLayer);
    state.markers.set(f.id, m);
  }
  for (const f of state.flagged) {
    L.circleMarker([f.lat, f.lon], { radius: 5, weight: 2, color: "#C2185B", fillColor: "#fff", fillOpacity: 0.6 })
      .bindTooltip(`Flagged location: far from the rest of ${f.epa} EPA`).addTo(flaggedLayer);
  }
  if (state.showFlagged) flaggedLayer.addTo(map);
}

function resetFarmerStyles(faded) {
  const c = colorOf(state.district);
  for (const m of state.markers.values()) m.setStyle({ radius: 3.6, weight: 0, fillColor: c, fillOpacity: faded ? 0.22 : 0.7 });
}

function drawVenues() {
  venueLayer.clearLayers();
  for (const v of state.venues) {
    if (!state.types.has(v.type)) continue;
    const t = TYPE[v.type] || TYPE.other;
    const marker = L.marker([v.lat, v.lon], {
      title: v.name, riseOnHover: true,
      icon: L.divIcon({ className: "", iconSize: [28, 28], iconAnchor: [14, 14], html: `<span class="vpin" style="--c:${t.color}">${iconHTML(t.icon)}</span>` }),
    });
    marker.bindPopup(() => el("div", { class: "popup" }, [
      el("strong", { text: v.name }),
      el("span", { text: t.one + (v.epa ? `, ${v.epa} EPA` : "") }),
      el("span", { text: v.fee != null ? `Hire fee ${mwk(v.fee)}` : "Hire fee not recorded" }),
      el("span", { text: { osm: "From OpenStreetMap", csv: "From your list", manual: "Added on the map" }[v.source] || "" }),
      el("div", { class: "row" }, [
        el("button", { type: "button", class: "btn btn-ink btn-small", text: "Check this venue", onclick: () => { map.closePopup(); runPlan({ name: v.name, lat: v.lat, lon: v.lon }); } }),
        el("button", { type: "button", class: "btn btn-ghost btn-small", text: "Remove", onclick: () => removeVenue(v) }),
      ]),
    ]));
    marker.addTo(venueLayer);
  }
}

function fitDistrict() {
  const pts = state.farmers.map((f) => [f.lat, f.lon]);
  if (state.hasOutline) {
    const b = L.latLngBounds([]);
    boundaryLayer.eachLayer((l) => b.extend(l.getBounds()));
    if (b.isValid()) { map.fitBounds(b, { padding: [30, 30] }); return; }
  }
  if (pts.length) map.fitBounds(pts, { padding: [50, 50], maxZoom: 13 });
}

function renderKpis() {
  const d = state.districts.find((x) => x.name === state.district);
  const box = $("kpis");
  box.replaceChildren();
  if (!d || !d.farmers) return;
  const kp = (b, s) => el("div", {}, [el("b", { text: b }), el("span", { text: s })]);
  box.append(kp(`${nf.format(d.mapped)} of ${nf.format(d.farmers)}`, "farmers on the map"),
    kp(String(state.epas.length), state.epas.length === 1 ? "EPA" : "EPAs"), kp(String(state.venues.length), "possible venues"));
}

function updateLegend() {
  const box = $("legend");
  box.replaceChildren();
  const row = (swatch, text) => el("div", { class: "row" }, [swatch, el("span", { text })]);
  const dot = (c) => el("i", { class: "sw", style: `background:${c}` });
  if (state.cohort && state.plan) {
    const w = readParams();
    box.append(el("div", { class: "ttl", text: "Trip length, one way by road" }));
    BANDS.forEach((b) => box.append(row(dot(b.color), b.label)));
    box.append(row(el("i", { class: "sw", style: "background:transparent;border:2px dashed #0D3B45" }), `Walk-in zone, ${w.walk_km} km by road`));
    box.append(row(dot("#9fb3b7"), "Not invited"));
  } else if (state.farmers.length) {
    box.append(row(dot(colorOf(state.district)), "Farmer home"));
    if (state.venues.length) box.append(row(dot("#2F6FD0"), "Possible venue"));
  }
}

// ------------------------------------------------------------ data pane
function switchRow(id, text, checked, onchange) {
  const input = el("input", { type: "checkbox", id });
  input.checked = checked;
  input.addEventListener("change", () => onchange(input.checked));
  return el("label", { class: "switch" }, [input, el("span", { text })]);
}

function renderData() {
  const root = $("pane-data");
  root.replaceChildren();
  const d = state.districts.find((x) => x.name === state.district);
  if (!d) { root.append(el("p", { class: "lede", text: "Choose a district above." })); return; }
  root.append(el("h2", { class: "h-pane", text: d.name }));
  if (!d.farmers) {
    root.append(
      el("p", { class: "lede", text: `No farmers have been imported for ${d.name} yet. Import the Solstice export to see them on the map.` }),
      el("div", { class: "venue-actions" }, el("button", { type: "button", class: "btn btn-yellow", text: "Import Solstice export", onclick: openImport })));
    return;
  }
  root.append(el("p", { class: "lede", text: state.epas.map((e) => e.epa + " EPA").join(" and ") + "." }));
  const fig = (b, s) => el("div", {}, [el("b", { text: nf.format(b) }), el("span", { text: s })]);
  root.append(el("div", { class: "figures" }, [fig(d.farmers, "farmers"), fig(d.mapped, "on the map"), fig(d.missing, "need a location")]));

  const notice = (text) => el("div", { class: "notice" }, [icon("warn"), el("p", { text })]);
  if (d.missing) root.append(notice(`${nf.format(d.missing)} farmers have no GPS location, so they cannot be mapped or invited. Ask field officers to capture their locations in Solstice.`));
  if (d.flagged) {
    root.append(notice(`${nf.format(d.flagged)} locations are far from the rest of their EPA and are probably GPS errors. They are left out of plans.`));
    root.append(switchRow("show-flagged", "Show the flagged locations on the map", state.showFlagged, (on) => {
      state.showFlagged = on;
      if (on) flaggedLayer.addTo(map); else map.removeLayer(flaggedLayer);
    }));
  }

  root.append(el("h3", { class: "h-sub", text: "EPAs" }));
  const list = el("ul", { class: "epa-list" });
  for (const e of state.epas) {
    const pct = (n) => (e.farmers ? (100 * n) / e.farmers : 0);
    const okN = e.mapped;
    list.append(el("li", {}, el("button", { type: "button", class: "epa-row", onclick: () => zoomEpa(e) }, [
      el("b", { text: `${e.epa} EPA` }),
      el("span", { class: "tot", text: `${nf.format(e.farmers)} farmers` }),
      el("div", { class: "stackbar", role: "img", "aria-label": `${okN} mapped, ${e.flagged} flagged, ${e.missing} without a location` }, [
        el("i", { style: `width:${pct(okN)}%;background:${colorOf(state.district)}` }),
        el("i", { style: `width:${pct(e.flagged)}%;background:#C2185B` }),
        el("i", { style: `width:${pct(e.missing)}%;background:#C3D3D6` })]),
      el("span", { class: "sub", text: `${nf.format(okN)} on the map, ${nf.format(e.flagged)} flagged, ${nf.format(e.missing)} without a location. ${Math.round(pct(e.women))}% women.` }),
    ])));
  }
  root.append(list);
  const estimated = state.epas.some((e) => e.outline_source === "estimated");
  root.append(el("p", { class: "hint", text: estimated
    ? "The dashed EPA areas are drawn around the mapped farmers. They are estimates, not official boundaries."
    : "The EPA areas shown are the official boundaries you uploaded." }));
  root.append(el("div", { class: "mini-links" }, [
    el("button", { type: "button", class: "linkbtn", text: "Upload official EPA boundaries", onclick: () => openFile("epa") }),
    el("button", { type: "button", class: "linkbtn", text: "Remove this district's data", onclick: removeDistrictData })]));

  root.append(el("h3", { class: "h-sub", text: "Possible venues" }));
  root.append(el("p", { class: "hint", text: state.venues.length
    ? `${state.venues.length} places near ${d.name}'s farmers. Choose which types to show and to consider in plans.`
    : "No venues yet. Find schools, cooperatives and other public places from OpenStreetMap, or add your own." }));
  root.append(el("div", { class: "venue-actions" }, [
    el("button", { type: "button", id: "btn-discover", class: "btn btn-yellow btn-small", text: "Find places on OpenStreetMap", onclick: discoverVenues }),
    el("button", { type: "button", class: "btn btn-ghost btn-small", text: "Import a list or boundaries", onclick: () => openFile("venues") }),
    el("button", { type: "button", id: "btn-addvenue", class: "btn btn-ghost btn-small", "aria-pressed": String(state.mode === "addvenue"), text: "Add a venue on the map", onclick: () => setMode("addvenue") })]));
  const counts = {};
  for (const v of state.venues) counts[v.type] = (counts[v.type] || 0) + 1;
  const chips = el("div", { class: "chips", role: "group", "aria-label": "Venue types" });
  for (const t of TYPES) {
    if (!counts[t.id]) continue;
    const ci = el("span", { class: "ci" }); ci.append(icon(t.icon));
    chips.append(el("button", { type: "button", class: "chip", style: `--c:${t.color}`, "aria-pressed": String(state.types.has(t.id)),
      onclick: () => { state.types.has(t.id) ? state.types.delete(t.id) : state.types.add(t.id); drawVenues(); renderData(); syncPlan(); } },
    [ci, el("span", { text: t.label }), el("small", { text: String(counts[t.id]) })]));
  }
  root.append(chips);
  if (state.venues.length) {
    root.append(el("div", { class: "mini-links" }, [
      el("button", { type: "button", class: "linkbtn", text: "Select all", onclick: () => { state.types = new Set(TYPES.map((t) => t.id)); drawVenues(); renderData(); syncPlan(); } }),
      el("button", { type: "button", class: "linkbtn", text: "Clear", onclick: () => { state.types.clear(); drawVenues(); renderData(); syncPlan(); } })]));
  }
}

function zoomEpa(e) {
  const g = state.epaLayers.get(e.epa);
  if (g) map.fitBounds(g.getBounds(), { padding: [40, 40], maxZoom: 14 });
}

async function removeDistrictData() {
  if (!confirm(`Remove all farmers, venues and saved scenarios for ${state.district} from the database? The Solstice file itself is not touched.`)) return;
  try {
    await api(`/districts?name=${encodeURIComponent(state.district)}`, { method: "DELETE" });
    await refreshDistricts(state.district);
    toast("District data removed.", "ok");
  } catch (e) { showError(e); }
}

async function discoverVenues() {
  const btn = $("btn-discover");
  btn.disabled = true; btn.textContent = "Searching OpenStreetMap\u2026";
  try {
    const r = await post("/venues/discover", { district: state.district, radius_km: 10 });
    state.venues = await api(`/venues?district=${encodeURIComponent(state.district)}`);
    state.districts = await api("/districts");
    drawVenues(); renderData(); syncPlan(); renderKpis(); renderTabs();
    toast(r.found_in_openstreetmap
      ? `OpenStreetMap lists ${r.found_in_openstreetmap} places in this area. ${r.added_or_updated} are within 10 km of a farmer and are now possible venues.`
      : "OpenStreetMap has no named schools, cooperatives or public places here. Add venues yourself or import a list.", r.added_or_updated ? "ok" : "warn");
  } catch (e) { showError(e); renderData(); }
}

async function removeVenue(v) {
  try {
    await api(`/venues/${v.id}`, { method: "DELETE" });
    state.venues = state.venues.filter((x) => x.id !== v.id);
    map.closePopup(); drawVenues(); renderData(); syncPlan(); renderKpis();
    toast(`${v.name} removed.`, "ok", 3000);
  } catch (e) { showError(e); }
}

// ------------------------------------------------------------ plan pane
function selectedEpas() { return state.epas.filter((e) => state.epaSel.size === 0 || state.epaSel.has(e.epa)); }
function scopeCount() {
  const inc = $("inc-flagged").checked;
  return selectedEpas().reduce((s, e) => s + e.mapped + (inc ? e.flagged : 0), 0);
}
function venueCount() { return state.venues.filter((v) => state.types.has(v.type)).length; }

function syncPlan() {
  const chips = $("epa-chips");
  chips.replaceChildren();
  const allChip = el("button", { type: "button", class: "chip plain", "aria-pressed": String(state.epaSel.size === 0), text: "All EPAs",
    onclick: () => { state.epaSel.clear(); syncPlan(); } });
  chips.append(allChip);
  for (const e of state.epas) {
    chips.append(el("button", { type: "button", class: "chip plain", "aria-pressed": String(state.epaSel.has(e.epa)),
      onclick: () => {
        state.epaSel.has(e.epa) ? state.epaSel.delete(e.epa) : state.epaSel.add(e.epa);
        if (state.epaSel.size === state.epas.length) state.epaSel.clear();
        syncPlan();
      } }, [el("span", { text: e.epa }), el("small", { text: nf.format(e.mapped) })]));
  }
  const count = scopeCount();
  const max = Math.max(1, count);
  $("n").max = max; $("n-range").max = max;
  if (count > 0 && Number($("n").value) > max) { $("n").value = max; $("n-range").value = max; }
  const everyone = $("all").checked;
  $("n").disabled = everyone; $("n-range").disabled = everyone;
  const names = state.epaSel.size ? [...state.epaSel].join(" and ") + " EPA" : state.district || "the district";
  $("scope-note").textContent = scopeCount()
    ? `${nf.format(scopeCount())} farmers in ${names} have a usable location. ${venueCount()} venues will be compared.`
    : "No mapped farmers yet. Import the Solstice export first.";
}

$("n").addEventListener("input", () => { $("n-range").value = $("n").value; });
$("n-range").addEventListener("input", () => { $("n").value = $("n-range").value; });
$("all").addEventListener("change", syncPlan);
$("inc-flagged").addEventListener("change", syncPlan);

function readParams() {
  const num = (id, fb) => { const el_ = $(id); const v = Number(el_.value); return el_.value !== "" && Number.isFinite(v) ? v : fb; };
  return { rate_per_km: num("p-rate", 100), refreshment: num("p-ref", 5000), default_venue_fee: num("p-fee", 0),
    walk_km: num("p-walk", 3), circuity: num("p-circ", 1.3) };
}
const objective = () => document.querySelector("input[name=obj]:checked").value;
const scopeBody = () => ({ district: state.district, epas: [...state.epaSel], include_flagged: $("inc-flagged").checked });

async function runPlan(extra) {
  if (!state.district || !scopeCount()) { toast("There are no mapped farmers to plan for yet. Import the Solstice export first.", "error"); return; }
  let n = null;
  if (!$("all").checked) {
    n = Number($("n").value);
    if (!Number.isInteger(n) || n < 1) { toast("Enter a whole number of farmers, 1 or more.", "error"); $("n").focus(); return; }
  }
  const btn = $("btn-plan");
  btn.disabled = true; btn.textContent = "Working it out\u2026";
  try {
    const res = await post("/plan", { ...scopeBody(), n, objective: objective(), params: readParams(),
      venue_types: [...state.types], no_venues: state.types.size === 0, extra_points: extra ? [extra] : [] });
    state.plan = res;
    showPane("results");
    renderResults();
    const idx = extra ? res.candidates.findIndex((c) => c.kind === "clicked") : 0;
    await selectCandidate(Math.max(idx, 0));
  } catch (e) { showError(e); } finally { btn.disabled = false; btn.textContent = "Find the best meeting place"; }
}

$("btn-plan").addEventListener("click", () => runPlan(null));
$("btn-test").addEventListener("click", () => setMode("test"));
map.on("click", (e) => {
  if (state.mode === "test") { setMode("test"); runPlan({ name: "Point you picked", lat: e.latlng.lat, lon: e.latlng.lng }); }
  else if (state.mode === "addvenue") openVenueDialog(e.latlng);
});

// ------------------------------------------------------------ results
const candStyle = (c) => (c.kind === "venue" ? TYPE[c.venue_type] || TYPE.other : KIND[c.kind]);

function renderResults() {
  const res = state.plan;
  const body = $("results-body");
  body.replaceChildren();
  $("results-empty").hidden = true; body.hidden = false;
  const top = res.candidates[0];
  const bestVenue = res.candidates.find((c) => c.kind === "venue");
  const reco = el("div", { class: "reco" }, [
    el("p", { class: "k", text: res.objective === "cost" ? "Lowest total cost" : "Shortest trip for the farthest farmer" }),
    el("p", { class: "big", text: top.name }),
    el("p", { text: `${plural(top.farmers, "farmer", "farmers")}, ${mwk(top.total_cost)} in total, farthest trip ${km1(top.max_km)}.` })]);
  if (top.kind !== "venue") {
    reco.append(el("p", { class: "alt", text: bestVenue
      ? `That spot is not an existing venue. The best actual venue is ${bestVenue.name}, ${bestVenue.total_cost > top.total_cost ? mwk(bestVenue.total_cost - top.total_cost) + " more" : "at the same cost"}, with a farthest trip of ${km1(bestVenue.max_km)}.`
      : "That spot is not an existing venue, and no venues are recorded yet. Find places near it, then plan again." }));
  }
  body.append(reco);
  const list = el("ol", { class: "rank" });
  let badged = false;
  res.candidates.forEach((c, i) => {
    const st = candStyle(c);
    const pin = el("span", { class: "pin" }); pin.append(icon(st.icon));
    const name = el("span", { class: "nm", text: c.name, title: c.name });
    if (c.kind === "venue" && !badged && top.kind !== "venue") { name.append(el("span", { class: "badge", text: "Best venue" })); badged = true; }
    list.append(el("li", {}, el("button", { type: "button", style: `--i:${i};--c:${st.color}`, "aria-current": String(i === state.selected), onclick: () => selectCandidate(i) }, [
      pin, name, el("span", { class: "cost", text: mwk(c.total_cost) }),
      el("span", { class: "meta", text: `${st.one}. Average ${km1(c.avg_km)}, farthest ${km1(c.max_km)}.` })])));
  });
  body.append(list, el("div", { id: "detail", class: "detail" }));
  if (res.venues_considered === 0) {
    body.append(el("p", { class: "hint", text: "No venues were compared. Find places on OpenStreetMap or add venues in the Data step." }));
  }
}

async function selectCandidate(i) {
  const c = state.plan.candidates[i];
  state.selected = i;
  for (const [k, b] of [...document.querySelectorAll(".rank button")].entries()) b.setAttribute("aria-current", String(k === i));
  try {
    const res = await post("/cohort", { ...scopeBody(), n: state.plan.n_used, lat: c.lat, lon: c.lon, fee: c.fee, params: readParams() });
    if (state.selected !== i) return;
    state.cohort = res;
    drawCohort(c, res);
    renderDetail(c, res);
    updateLegend();
  } catch (e) { showError(e); }
}

function drawCohort(c, res) {
  resetFarmerStyles(true);
  siteLayer.clearLayers();
  const bounds = [[c.lat, c.lon]];
  for (const a of res.attendees) {
    state.markers.get(a.id)?.setStyle({ radius: 5.5, weight: 1.5, color: "#fff", fillColor: BANDS[a.band].color, fillOpacity: 1 });
    bounds.push([a.lat, a.lon]);
  }
  const p = readParams();
  L.circle([c.lat, c.lon], { radius: (p.walk_km / p.circuity) * 1000, color: "#0D3B45", weight: 1.6, dashArray: "5 5", fillColor: "#0D3B45", fillOpacity: 0.05, interactive: false }).addTo(siteLayer);
  const site = L.marker([c.lat, c.lon], { title: c.name, zIndexOffset: 1000,
    icon: L.divIcon({ className: "", iconSize: [26, 26], iconAnchor: [13, 13], html: '<span class="site-pin"></span>' }) });
  site.bindPopup(() => el("div", { class: "popup" }, [el("strong", { text: c.name }), el("span", { text: candStyle(c).one }),
    el("span", { text: `${c.lat.toFixed(5)}, ${c.lon.toFixed(5)}` })]));
  site.addTo(siteLayer);
  sweepLines(res.attendees, c);
  map.fitBounds(bounds, { padding: [60, 60], maxZoom: 13 });
}

function sweepLines(attendees, c) {
  lineLayer.clearLayers();
  const token = ++state.sweep;
  if (attendees.length > MAX_LINES) return;
  const sorted = [...attendees].sort((a, b) => a.road_km - b.road_km);
  const chunk = reduceMotion() ? sorted.length : Math.ceil(sorted.length / 18);
  let i = 0;
  const step = () => {
    if (token !== state.sweep) return;
    for (const end = Math.min(i + chunk, sorted.length); i < end; i++) {
      const a = sorted[i];
      L.polyline([[a.lat, a.lon], [c.lat, c.lon]], { color: BANDS[a.band].color, weight: 1.5, opacity: 0.6, interactive: false }).addTo(lineLayer);
    }
    if (i < sorted.length) requestAnimationFrame(step);
  };
  step();
}

function countUp(node, to) {
  if (reduceMotion()) { node.textContent = mwk(to); return; }
  const t0 = performance.now();
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / 600);
    node.textContent = mwk(to * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function renderDetail(c, res) {
  const s = res.summary, p = readParams();
  const box = $("detail");
  box.replaceChildren();
  const tile = (label, value, cls = "") => el("div", { class: "tile " + cls }, [el("dt", { text: label }), el("dd", { text: value })]);
  const hero = tile("Total cost", mwk(0), "hero");
  const bandRows = BANDS.map((b, i) => el("div", { class: "band" }, [
    el("i", { class: "sw", style: `background:${b.color}` }), el("span", { text: b.label }),
    el("div", { class: "bar", role: "img", "aria-label": `${b.label}: ${res.bands[i]} farmers` },
      el("span", { style: `width:${(100 * res.bands[i]) / s.farmers}%;background:${b.color}` })),
    el("b", { text: String(res.bands[i]) })]));
  const mix = Object.entries(res.by_epa).map(([e, n]) => `${e} ${n}`).join(", ");
  box.append(
    el("h3", { text: c.name }),
    el("p", { class: "sub", text: `${candStyle(c).one}${c.venue_epa ? ", " + c.venue_epa + " EPA" : ""}. ${c.lat.toFixed(5)}, ${c.lon.toFixed(5)}` }),
    el("dl", { class: "tiles" }, [hero, tile("Per farmer", mwk(s.per_farmer)), tile("Transport", mwk(s.transport_cost)),
      tile("Refreshments", mwk(s.refreshments)), tile("Venue fee", c.kind === "venue" && !c.fee_known && p.default_venue_fee ? mwk(s.venue_fee) + " (assumed)" : mwk(s.venue_fee)),
      tile("Average trip", km1(s.avg_km)), tile("Farthest trip", km1(s.max_km))]),
    el("h4", { class: "h-sub", text: "Trip length, one way by road" }),
    el("div", { class: "bands" }, bandRows),
    el("p", { class: "mixline", text: `${s.walkers} of ${s.farmers} walk in (within ${p.walk_km} km by road).` }),
    el("p", { class: "mixline", text: `Invited from ${mix}. ${s.women} are women. ${s.with_phone} have a phone number on file.` }),
    el("p", { class: "hint", text: `Road distance is straight-line distance times ${p.circuity}.` + (c.kind === "venue" ? "" : " Look for a school, church or hall near this point, then add it as a venue to compare.") }),
    el("div", { class: "stack" }, [
      el("button", { type: "button", class: "btn btn-ink btn-wide", text: "Download the attendee list", onclick: downloadAttendees }),
      el("button", { type: "button", class: "btn btn-ghost btn-wide", text: "Save this scenario", onclick: saveScenario })]));
  countUp(hero.querySelector("dd"), s.total_cost);
}

// ------------------------------------------------------------ scenarios and export
async function saveScenario() {
  const c = state.plan?.candidates[state.selected], res = state.cohort;
  if (!c || !res) return;
  try {
    await post("/scenarios", { district: state.district, epas: [...state.epaSel], n_farmers: res.summary.farmers, objective: objective(),
      site_name: c.name, lat: c.lat, lon: c.lon, total_cost: res.summary.total_cost, avg_km: res.summary.avg_km,
      max_km: res.summary.max_km, params: readParams() });
    toast("Scenario saved. Find it under Saved scenarios in Results.", "ok");
    loadScenarios();
  } catch (e) { showError(e); }
}

async function loadScenarios() {
  if (!state.district) return;
  try {
    const rows = await api(`/scenarios?district=${encodeURIComponent(state.district)}`);
    const list = $("saved");
    list.replaceChildren();
    for (const r of rows) {
      list.append(el("li", {}, [
        el("div", { text: `${r.site_name}: ${r.n_farmers} farmers, ${mwk(r.total_cost)}` }),
        el("div", { class: "when", text: `Average ${km1(r.avg_km)}, farthest ${km1(r.max_km)}. ${new Date(r.created_at).toLocaleString()}` })]));
    }
    $("saved-wrap").hidden = rows.length === 0;
  } catch (e) { console.error(e); }
}

function csvCell(v) {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function downloadAttendees() {
  const c = state.plan?.candidates[state.selected], res = state.cohort;
  if (!c || !res) return;
  const head = ["solstice_serial", "name", "sex", "phone", "epa", "ward", "village", "road_km_one_way", "walks_in", "round_trip_transport_mwk"];
  const lines = [head.join(",")].concat(res.attendees.map((a) =>
    [a.serial, a.name, a.sex, a.phone, a.epa, a.ward, a.village, a.road_km, a.walks ? "yes" : "no", a.transport_cost].map(csvCell).join(",")));
  const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv" });
  const a = el("a", { href: URL.createObjectURL(blob), download: `attendees_${state.district}_${c.name}.csv`.replace(/[^\w.-]+/g, "_") });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast(`Attendee list downloaded. It contains names and phone numbers, so handle it with care.`, "ok");
}

// ------------------------------------------------------------ import Solstice dialog
const dlgImport = $("dlg-import");
let pendingFile = null;

function setFile(f) {
  pendingFile = f;
  $("file-name").textContent = f ? `${f.name} (${Math.max(1, Math.round(f.size / 1024))} KB)` : "";
  $("import-go").disabled = !f;
  $("import-report").replaceChildren();
  state.importDone = null;
  $("import-close").textContent = "Close";
  $("import-close").className = "btn btn-ghost";
  $("import-go").hidden = false;
}
function openImport() { setFile(null); $("file-solstice").value = ""; dlgImport.showModal(); }
$("btn-import").addEventListener("click", openImport);
$("import-close").addEventListener("click", () => dlgImport.close());
dlgImport.addEventListener("close", async () => {
  if (!state.importDone) return;
  const imported = state.importDone;
  state.importDone = null;
  // open the first project district (Salima, Mangochi, Balaka order) that was in the file
  const first = state.districts.find((d) => imported.includes(d.name));
  await refreshDistricts(first ? first.name : imported[0]);
});
$("file-solstice").addEventListener("change", (e) => { if (e.target.files[0]) setFile(e.target.files[0]); });
for (const zone of [$("drop"), $("drop-welcome")]) {
  zone.addEventListener("click", () => $("file-solstice").click());
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file-solstice").click(); } });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault(); zone.classList.remove("over");
    const f = e.dataTransfer.files[0];
    if (!f) return;
    if (zone.id === "drop-welcome") openImport();
    setFile(f);
  });
}
$("file-solstice").addEventListener("click", (e) => e.stopPropagation());
document.addEventListener("change", (e) => { if (e.target.id === "file-solstice" && e.target.files[0] && !dlgImport.open) { dlgImport.showModal(); } });

function reportEl(r) {
  const root = el("div", { class: "report" });
  root.append(el("p", { text: `Read ${nf.format(r.rows_read)} rows and imported ${nf.format(r.imported)}.` }));
  const s = r.coordinate_sources;
  root.append(el("p", { text: `Locations: ${nf.format(s.gps)} from GPS, ${nf.format(s.household)} from the household-size capture, ${nf.format(s.phase1)} from the phase 1 question, ${nf.format(s.none)} with none.` }));
  const table = el("table", {}, [el("thead", {}, el("tr", {}, ["EPA", "Farmers", "On the map", "Flagged", "No location"].map((h) => el("th", { text: h })))),
    el("tbody", {}, r.areas.map((a) => el("tr", {}, [`${a.epa} (${a.district})`, nf.format(a.farmers), nf.format(a.mapped), nf.format(a.flagged), nf.format(a.missing)].map((t) => el("td", { text: t })))))]);
  root.append(table);
  const notes = [];
  for (const [from, to] of Object.entries(r.corrections)) notes.push(`Corrected the spelling "${from}" to "${to}".`);
  if (r.duplicates) notes.push(`${r.duplicates} duplicate serial numbers in the file were merged.`);
  if (r.rejected) notes.push(`${r.rejected} rows were skipped. ${r.rejected_examples[0] || ""}`);
  notes.push(...r.warnings);
  if (notes.length) root.append(el("ul", {}, notes.map((n) => el("li", { text: n }))));
  return root;
}

async function doImport() {
  if (!pendingFile) return;
  const btn = $("import-go");
  btn.disabled = true; btn.textContent = "Importing\u2026";
  $("import-report").replaceChildren(el("p", { class: "hint", text: "Reading the file and checking locations\u2026" }));
  const fd = new FormData();
  fd.append("file", pendingFile);
  fd.append("replace", $("opt-replace").checked ? "true" : "false");
  fd.append("outlier_km", $("opt-km").value || "30");
  try {
    const r = await api("/import/solstice", { method: "POST", body: fd });
    $("import-report").replaceChildren(reportEl(r));
    state.importDone = [...new Set(r.areas.map((a) => a.district))];
    $("import-close").textContent = "Open the map";
    $("import-close").className = "btn btn-ink";
    $("import-go").hidden = true;
  } catch (e) {
    $("import-report").replaceChildren(el("p", { class: "msg error", text: e.message }));
  } finally { btn.disabled = false; btn.textContent = "Import"; }
}
$("import-go").addEventListener("click", doImport);

$("btn-sample").addEventListener("click", async () => {
  try {
    const res = await fetch(ORIGIN + "/samples/sample_solstice_export.xlsx");
    if (!res.ok) throw new Error("The sample file is missing from this install.");
    const blob = await res.blob();
    openImport();
    setFile(new File([blob], "sample_solstice_export.xlsx", { type: blob.type }));
    await doImport();
  } catch (e) { showError(e); }
});

// ------------------------------------------------------------ import list or boundaries dialog
const dlgFile = $("dlg-file");
const FILE_HELP = {
  venues: "A CSV with name, lat and lon columns, and optionally type (school, church, cooperative, market and so on) and fee in MWK. The first row can be a header.",
  epa: "A GeoJSON file of EPA polygons in WGS84 (EPSG:4326). Each EPA needs a name property such as name or EPA. Only EPAs found in this district are kept.",
  district: "A GeoJSON file with the district polygon (WGS84). If the file holds many districts, the one named after this district is kept.",
};
const ftype = () => document.querySelector("input[name=ftype]:checked").value;
function updateFileHelp() { $("file-help").textContent = FILE_HELP[ftype()]; $("file-msg").textContent = ""; $("file-msg").className = "msg"; }
function openFile(type) {
  if (!state.district) { toast("Choose a district first.", "warn"); return; }
  document.querySelector(`input[name=ftype][value=${type}]`).checked = true;
  $("file-other").value = "";
  updateFileHelp();
  dlgFile.showModal();
}
for (const r of document.querySelectorAll("input[name=ftype]")) r.addEventListener("change", updateFileHelp);
$("file-close").addEventListener("click", () => dlgFile.close());
function fileMsg(text, kind = "") { $("file-msg").textContent = text; $("file-msg").className = "msg " + kind; }

$("file-go").addEventListener("click", async () => {
  const f = $("file-other").files[0];
  if (!f) { fileMsg("Choose a file first.", "error"); return; }
  const text = await f.text();
  const btn = $("file-go");
  btn.disabled = true;
  try {
    if (ftype() === "venues") {
      const parsed = CsvParse.parseVenues(text);
      if (!parsed.rows.length) {
        const why = parsed.rejected[0] ? ` First problem: line ${parsed.rejected[0].line}, ${parsed.rejected[0].reason}.` : "";
        fileMsg("No usable venues found." + why, "error");
        return;
      }
      await post("/venues/import", { district: state.district, rows: parsed.rows.map((r) => ({ ...r, district: state.district })) });
      toast(`Imported ${parsed.rows.length} venues.` + (parsed.rejected.length ? ` ${parsed.rejected.length} rows were skipped.` : ""), "ok");
    } else {
      let gj;
      try { gj = JSON.parse(text); } catch { fileMsg("That file is not valid GeoJSON.", "error"); return; }
      const r = await post("/boundaries/import", { district: state.district, level: ftype(), geojson: gj });
      toast(`Boundary loaded: ${r.imported.join(", ")}.`, "ok");
    }
    dlgFile.close();
    state.triedBoundary.add(state.district);
    await refreshDistricts(state.district);
  } catch (e) { fileMsg(e.message, "error"); } finally { btn.disabled = false; }
});

// ------------------------------------------------------------ add venue dialog
const dlgVenue = $("dlg-venue");
for (const t of TYPES) $("v-type").append(el("option", { value: t.id, text: t.one }));
function openVenueDialog(latlng) {
  state.pendingVenue = { lat: latlng.lat, lon: latlng.lng };
  $("venue-where").textContent = `Location ${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
  $("v-name").value = ""; $("v-fee").value = ""; $("venue-msg").textContent = "";
  dlgVenue.showModal();
  $("v-name").focus();
}
$("venue-cancel").addEventListener("click", () => { dlgVenue.close(); });
$("venue-save").addEventListener("click", async () => {
  const name = $("v-name").value.trim();
  if (!name) { $("venue-msg").textContent = "Enter the venue's name."; $("venue-msg").className = "msg error"; $("v-name").focus(); return; }
  const fee = $("v-fee").value === "" ? null : Number($("v-fee").value);
  try {
    await post("/venues", { district: state.district, name, type: $("v-type").value, fee, ...state.pendingVenue });
    state.venues = await api(`/venues?district=${encodeURIComponent(state.district)}`);
    dlgVenue.close(); setMode(null);
    drawVenues(); renderData(); syncPlan(); renderKpis();
    toast(`${name} added as a possible venue.`, "ok");
  } catch (e) { $("venue-msg").textContent = e.message; $("venue-msg").className = "msg error"; }
});

// ------------------------------------------------------------ start
(async () => {
  try { await refreshDistricts(null); }
  catch (e) {
    showError(e);
    $("pane-data").replaceChildren(el("h2", { class: "h-pane", text: "Cannot reach the database" }),
      el("p", { class: "lede", text: "Open http://localhost:8000 in your browser and check that Docker Desktop is running. The README explains how." }));
  }
})();
