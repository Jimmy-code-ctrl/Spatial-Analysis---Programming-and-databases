"""OpenStreetMap (Overpass API) helpers: district boundaries and candidate venues."""
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
USER_AGENT = "training-site-planner/1.0 (MSc GIS coursework, AICC Malawi)"


class OverpassError(Exception):
    pass


def run_query(query: str, timeout: int = 100) -> dict:
    """POST an Overpass query, trying mirrors in turn.

    For offline demos and automated tests, set OSM_FIXTURE to a JSON file shaped like
    {"boundary": <overpass json>, "venues": <overpass json>} and no internet is used."""
    fixture = os.environ.get("OSM_FIXTURE")
    if fixture:
        with open(fixture, encoding="utf-8") as fh:
            data = json.load(fh)
        return data["boundary"] if '"boundary"="administrative"' in query else data["venues"]
    body = urllib.parse.urlencode({"data": query}).encode()
    errors = []
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            errors.append(f"{urllib.parse.urlparse(url).netloc}: {e.__class__.__name__}")
    raise OverpassError(
        "Could not reach OpenStreetMap right now (" + "; ".join(errors) + "). "
        "Check the internet connection of the computer running Docker, then try again in a minute.")


# ---------------------------------------------------------------- district boundary
def boundary_query(district: str) -> str:
    name = re.sub(r"[^A-Za-z' -]", "", district).strip()
    return (
        "[out:json][timeout:90];\n"
        f'rel["boundary"="administrative"]["admin_level"~"^[4-7]$"]["name"~"^{name}( District)?$",i];\n'
        "out geom;"
    )


def relation_wkts(data: dict):
    """One MULTILINESTRING WKT per relation found (the database builds the polygon)."""
    found = []
    for el in data.get("elements", []):
        if el.get("type") != "relation":
            continue
        lines = []
        for m in el.get("members", []):
            geom = m.get("geometry")
            if m.get("type") == "way" and geom and len(geom) >= 2:
                lines.append("(" + ",".join(f"{p['lon']} {p['lat']}" for p in geom) + ")")
        if lines:
            found.append(((el.get("tags") or {}).get("name", ""), "MULTILINESTRING(" + ",".join(lines) + ")"))
    return found


# ---------------------------------------------------------------- venues
AMENITIES = ("school|college|kindergarten|community_centre|townhall|marketplace|place_of_worship|"
             "clinic|hospital|doctors|social_facility")
NAME_HINTS = "co-?operative|coop|admarc|extension|agricultur|farmers"


def venues_query(south, west, north, east) -> str:
    box = f"({south:.5f},{west:.5f},{north:.5f},{east:.5f})"
    return (
        "[out:json][timeout:90];\n(\n"
        f'  nwr["amenity"~"^({AMENITIES})$"]["name"]{box};\n'
        f'  nwr["office"~"^(government|cooperative|ngo|association)$"]["name"]{box};\n'
        f'  nwr["name"~"{NAME_HINTS}",i]{box};\n'
        ");\nout center tags;"
    )


def classify(tags: dict):
    name = (tags.get("name") or "").lower()
    amenity, office = tags.get("amenity"), tags.get("office")
    if office == "cooperative" or re.search(r"co-?operative|\bcoop\b|farmers'? ?(club|association|union)", name):
        return "cooperative"
    if amenity in ("school", "college", "kindergarten"):
        if "primary" in name or tags.get("isced:level") in ("1", "0;1", "1;2"):
            return "primary_school"
        if "secondary" in name or re.search(r"\bcss\b|\bdss\b", name):
            return "secondary_school"
        return "school"
    if amenity in ("community_centre", "townhall", "social_facility"):
        return "community_hall"
    if amenity == "marketplace" or re.search(r"admarc|market", name):
        return "market"
    if amenity == "place_of_worship":
        return "worship"
    if amenity in ("clinic", "hospital", "doctors") or tags.get("healthcare"):
        return "health_centre"
    if office == "government" or re.search(r"extension|agricultur|\bepa\b|district council", name):
        return "extension_office"
    if office in ("ngo", "association"):
        return "other"
    return None


def parse_venues(data: dict):
    out, seen = [], set()
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        vtype = classify(tags)
        if not name or not vtype:
            continue
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        oid = f"{el.get('type')}/{el.get('id')}"
        if oid in seen:
            continue
        seen.add(oid)
        out.append({"osm_id": oid, "name": name, "type": vtype, "lat": float(lat), "lon": float(lon)})
    return out


def padded_bbox(west, south, east, north, margin_km):
    dlat = margin_km / 110.574
    dlon = margin_km / (111.320 * math.cos(math.radians((south + north) / 2)))
    return south - dlat, west - dlon, north + dlat, east + dlon
