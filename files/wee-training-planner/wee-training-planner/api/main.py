"""Training Site Planner API (WEECVC cotton project).

Imports a Solstice beneficiary export, maps farmers by district and EPA, finds
possible venues (OpenStreetMap or your own list) and works out where to hold a
training for N farmers and what mobilising them will cost.

PostGIS does the spatial work. Python builds candidate sites and cost summaries.
"""
import bisect
import os
import random
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import geo
import osm
import solstice

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://gis:gis@localhost:5433/weeplanner")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# The WEECVC project areas: district -> EPAs
PROJECT = {
    "Salima": ["Chipoka", "Chigulukwe"],
    "Mangochi": ["Nankumba"],
    "Balaka": ["Rivirivi"],
}
VENUE_TYPES = ["primary_school", "secondary_school", "school", "cooperative", "community_hall",
               "worship", "market", "health_centre", "extension_office", "other"]
VENUE_ALIASES = {"church": "worship", "mosque": "worship", "hall": "community_hall",
                 "clinic": "health_centre", "hospital": "health_centre", "admarc": "market"}
BAND_EDGES_KM = [2, 5, 10, 20]  # road km, one way -> 5 bands
MAX_UPLOAD = 25 * 1024 * 1024

app = FastAPI(title="Training Site Planner API")
# Demo only: lets the page work if opened from disk or another dev server.
# Restrict allow_origins before any real deployment.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@contextmanager
def cursor():
    """One short-lived connection per request; commits on success."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


def norm_type(t: str) -> str:
    t = (t or "").strip().lower().replace(" ", "_").replace("-", "_")
    t = VENUE_ALIASES.get(t, t)
    return t if t in VENUE_TYPES else "other"


# ------------------------------------------------------------------ models
class Params(BaseModel):
    rate_per_km: float = Field(100, ge=0, le=1_000_000, description="transport cost per road km")
    circuity: float = Field(1.3, ge=1, le=3, description="road km = straight-line km x this")
    walk_km: float = Field(3, ge=0, le=50, description="farmers within this road distance walk (no transport cost)")
    refreshment: float = Field(5000, ge=0, le=10_000_000, description="meal/refreshment cost per farmer")
    default_venue_fee: float = Field(0, ge=0, le=10_000_000, description="fee used when a venue has no fee recorded")


class Scope(BaseModel):
    district: str = Field(min_length=1, max_length=80)
    epas: list[str] = Field(default_factory=list, max_length=20)
    include_flagged: bool = False


class PointIn(BaseModel):
    name: str = Field("Your point", max_length=80)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class PlanIn(Scope):
    n: Optional[int] = Field(None, ge=1, le=100_000, description="farmers to mobilise; null = everyone")
    objective: Literal["cost", "fairness"] = "cost"
    params: Params = Field(default_factory=Params)
    venue_types: list[str] = Field(default_factory=list, max_length=20)
    no_venues: bool = False
    extra_points: list[PointIn] = Field(default_factory=list, max_length=5)


class CohortIn(Scope):
    n: int = Field(ge=1, le=100_000)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    fee: float = Field(0, ge=0)
    params: Params = Field(default_factory=Params)


class VenueIn(BaseModel):
    district: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    type: str = "other"
    fee: Optional[float] = Field(None, ge=0, le=1e9)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class VenueImport(BaseModel):
    district: str = Field(min_length=1, max_length=80)
    replace: bool = False
    rows: list[VenueIn] = Field(min_length=1, max_length=2_000)


class DiscoverIn(BaseModel):
    district: str = Field(min_length=1, max_length=80)
    radius_km: float = Field(10, gt=0, le=40, description="keep places within this distance of a farmer")


class DistrictIn(BaseModel):
    district: str = Field(min_length=1, max_length=80)


class BoundaryImport(BaseModel):
    district: str = Field(min_length=1, max_length=80)
    level: Literal["district", "epa"]
    geojson: dict
    name_property: Optional[str] = None


class ScenarioIn(BaseModel):
    district: str
    epas: list[str] = Field(default_factory=list)
    n_farmers: int = Field(ge=1)
    objective: Literal["cost", "fairness"]
    site_name: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    total_cost: float = Field(ge=0)
    avg_km: float = Field(ge=0)
    max_km: float = Field(ge=0)
    params: Params


def scope_sql(alias="f"):
    """WHERE-clause for 'the farmers this plan is about'. Params: district, epas, flagged, all_epas."""
    return (f"{alias}.district = %(district)s AND {alias}.geom IS NOT NULL "
            f"AND (%(flagged)s OR {alias}.quality = 'ok') "
            f"AND (%(all_epas)s OR {alias}.epa = ANY(%(epas)s))")


def scope_params(s: Scope):
    return {"district": s.district, "epas": s.epas, "all_epas": not s.epas, "flagged": s.include_flagged}


# ------------------------------------------------------------------ project, districts, EPAs
@app.get("/api/project")
def project():
    return {"districts": PROJECT, "venue_types": VENUE_TYPES}


@app.get("/api/districts")
def districts():
    with cursor() as cur:
        cur.execute(
            "SELECT d.name, "
            "  (SELECT count(*) FROM farmers f WHERE f.district = d.name)::int AS farmers, "
            "  (SELECT count(*) FROM farmers f WHERE f.district = d.name AND f.quality = 'ok')::int AS mapped, "
            "  (SELECT count(*) FROM farmers f WHERE f.district = d.name AND f.quality = 'missing')::int AS missing, "
            "  (SELECT count(*) FROM farmers f WHERE f.district = d.name AND f.quality = 'outlier')::int AS flagged, "
            "  (SELECT count(*) FROM venues v WHERE v.district = d.name)::int AS venues, "
            "  EXISTS (SELECT 1 FROM boundaries b WHERE b.level = 'district' AND b.district = d.name) AS has_boundary "
            "FROM (SELECT unnest(%s::text[]) AS name UNION SELECT district FROM farmers "
            "      UNION SELECT district FROM venues) d",
            (list(PROJECT),),
        )
        rows = cur.fetchall()
        cur.execute("SELECT DISTINCT district, epa FROM farmers ORDER BY epa")
        found = cur.fetchall()
    for r in rows:
        epas = list(PROJECT.get(r["name"], []))
        epas += [x["epa"] for x in found if x["district"] == r["name"] and x["epa"] not in epas]
        r["epas"] = epas
    order = list(PROJECT)
    rows.sort(key=lambda r: (order.index(r["name"]) if r["name"] in order else 99, r["name"]))
    return rows


@app.delete("/api/districts", status_code=204)
def delete_district(name: str = Query(min_length=1)):
    with cursor() as cur:
        for table in ("farmers", "venues", "scenarios"):
            cur.execute(f"DELETE FROM {table} WHERE district = %s", (name,))


@app.get("/api/epas")
def epas(district: str = Query(min_length=1)):
    """One row per EPA: counts, data quality, and its map area (official boundary if
    uploaded, otherwise an outline drawn around the mapped farmers)."""
    with cursor() as cur:
        cur.execute(
            "SELECT f.epa, count(*)::int AS farmers, "
            "  (count(*) FILTER (WHERE f.quality = 'ok'))::int AS mapped, "
            "  (count(*) FILTER (WHERE f.quality = 'missing'))::int AS missing, "
            "  (count(*) FILTER (WHERE f.quality = 'outlier'))::int AS flagged, "
            "  (count(*) FILTER (WHERE f.sex = 'Female'))::int AS women, "
            "  ST_AsGeoJSON(ST_Multi(ST_Buffer(ST_ConcaveHull(ST_Collect(f.geom) FILTER (WHERE f.quality = 'ok'), 0.75)"
            "     ::geography, 400)::geometry))::json AS outline, "
            "  ST_Y(ST_Centroid(ST_Collect(f.geom) FILTER (WHERE f.quality = 'ok')))::float8 AS lat, "
            "  ST_X(ST_Centroid(ST_Collect(f.geom) FILTER (WHERE f.quality = 'ok')))::float8 AS lon "
            "FROM farmers f WHERE f.district = %s GROUP BY f.epa ORDER BY f.epa",
            (district,),
        )
        rows = cur.fetchall()
        cur.execute(
            "SELECT name, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0003))::json AS g "
            "FROM boundaries WHERE level = 'epa' AND district = %s", (district,))
        official = {r["name"].lower().removesuffix(" epa").strip(): r["g"] for r in cur.fetchall()}
    for r in rows:
        key = r["epa"].lower()
        r["outline_source"] = "official" if key in official else "estimated"
        if key in official:
            r["outline"] = official[key]
    return rows


@app.get("/api/farmers")
def farmers(district: str = Query(min_length=1), include_flagged: bool = True):
    """Map points only. Names and phone numbers are NOT sent here."""
    with cursor() as cur:
        cur.execute(
            "SELECT id, epa, ward, village, sex, quality, "
            "ST_X(geom)::float8 AS lon, ST_Y(geom)::float8 AS lat "
            "FROM farmers WHERE district = %s AND geom IS NOT NULL AND (%s OR quality = 'ok') ORDER BY id",
            (district, include_flagged),
        )
        return cur.fetchall()


# ------------------------------------------------------------------ Solstice import
QUALITY_SQL = """
WITH med AS (
  SELECT district, epa,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_X(geom)) AS lon,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_Y(geom)) AS lat
  FROM farmers WHERE geom IS NOT NULL AND district = ANY(%(districts)s) GROUP BY district, epa)
UPDATE farmers f SET quality = CASE
    WHEN f.geom IS NULL THEN 'missing'
    WHEN ST_Distance(f.geom::geography, ST_SetSRID(ST_MakePoint(m.lon, m.lat), 4326)::geography) > %(m)s THEN 'outlier'
    ELSE 'ok' END
FROM med m
WHERE f.district = m.district AND f.epa = m.epa AND f.district = ANY(%(districts)s)
"""


def assign_venue_epas(cur, district):
    """Give each venue the EPA of its nearest mapped farmer (if one is within 10 km)."""
    cur.execute(
        "UPDATE venues v SET epa = n.epa FROM ( "
        "  SELECT v2.id, (SELECT f.epa FROM farmers f "
        "                 WHERE f.district = v2.district AND f.quality = 'ok' "
        "                   AND ST_DWithin(f.geom::geography, v2.geom::geography, 10000) "
        "                 ORDER BY f.geom::geography <-> v2.geom::geography LIMIT 1) AS epa "
        "  FROM venues v2 WHERE v2.district = %s) n "
        "WHERE v.id = n.id", (district,))


@app.post("/api/import/solstice")
def import_solstice(file: UploadFile = File(...), replace: bool = Form(False), outlier_km: float = Form(30)):
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "That file is larger than 25 MB.")
    try:
        parsed = solstice.parse(data, file.filename or "")
    except solstice.ImportProblem as e:
        raise HTTPException(422, str(e))

    areas = sorted({(r["district"], r["epa"]) for r in parsed.records})
    dists = sorted({d for d, _ in areas})
    rows = [(r["district"], r["epa"], r["ward"], r["village"], r["serial"], r["name"], r["sex"], r["phone"],
             r["category"], r["value_chain"], r["coord_source"], r["accuracy_m"], r["wkt"])
            for r in parsed.records]
    with cursor() as cur:
        if replace:
            cur.execute("DELETE FROM farmers WHERE (district, epa) IN %s", (tuple(areas),))
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO farmers (district, epa, ward, village, serial, name, sex, phone, category, value_chain, "
            "                     coord_source, accuracy_m, geom, quality) VALUES %s "
            "ON CONFLICT (district, epa, serial) DO UPDATE SET ward = EXCLUDED.ward, village = EXCLUDED.village, "
            "  name = EXCLUDED.name, sex = EXCLUDED.sex, phone = EXCLUDED.phone, category = EXCLUDED.category, "
            "  value_chain = EXCLUDED.value_chain, coord_source = EXCLUDED.coord_source, "
            "  accuracy_m = EXCLUDED.accuracy_m, geom = EXCLUDED.geom, quality = EXCLUDED.quality, imported_at = now()",
            [r + ("ok" if r[-1] else "missing",) for r in rows],  # quality is refined below
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)",
            page_size=500,
        )
        cur.execute(QUALITY_SQL, {"districts": dists, "m": outlier_km * 1000})
        for d in dists:
            assign_venue_epas(cur, d)
        cur.execute(
            "SELECT district, epa, count(*)::int AS farmers, "
            "  (count(*) FILTER (WHERE quality = 'ok'))::int AS mapped, "
            "  (count(*) FILTER (WHERE quality = 'missing'))::int AS missing, "
            "  (count(*) FILTER (WHERE quality = 'outlier'))::int AS flagged "
            "FROM farmers WHERE (district, epa) IN %s GROUP BY district, epa ORDER BY district, epa", (tuple(areas),))
        by_area = cur.fetchall()
    order = list(PROJECT)
    by_area.sort(key=lambda a: (order.index(a["district"]) if a["district"] in order else 99, a["epa"]))
    return {
        "rows_read": parsed.rows_read, "imported": len(parsed.records), "duplicates": parsed.duplicates,
        "rejected": len(parsed.rejected), "rejected_examples": [f"Row {n}: {why}" for n, why in parsed.rejected[:5]],
        "coordinate_sources": parsed.sources, "corrections": parsed.corrections,
        "warnings": parsed.warnings, "areas": by_area, "outlier_km": outlier_km,
    }


# ------------------------------------------------------------------ venues
@app.get("/api/venues")
def venues(district: str = Query(min_length=1)):
    with cursor() as cur:
        cur.execute(
            "SELECT id, name, type, epa, source, fee_mwk::float8 AS fee, "
            "ST_X(geom)::float8 AS lon, ST_Y(geom)::float8 AS lat "
            "FROM venues WHERE district = %s ORDER BY name", (district,))
        return cur.fetchall()


@app.post("/api/venues", status_code=201)
def add_venue(v: VenueIn):
    with cursor() as cur:
        cur.execute(
            "INSERT INTO venues (district, name, type, fee_mwk, source, geom) "
            "VALUES (%s, %s, %s, %s, 'manual', ST_SetSRID(ST_MakePoint(%s, %s), 4326)) RETURNING id",
            (v.district, v.name.strip(), norm_type(v.type), v.fee, v.lon, v.lat))
        new_id = cur.fetchone()["id"]
        assign_venue_epas(cur, v.district)
        return {"id": new_id}


@app.delete("/api/venues/{venue_id}", status_code=204)
def remove_venue(venue_id: int):
    with cursor() as cur:
        cur.execute("DELETE FROM venues WHERE id = %s", (venue_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Venue not found")


@app.post("/api/venues/import", status_code=201)
def import_venues(body: VenueImport):
    data = [(body.district, r.name.strip(), norm_type(r.type), r.fee, r.lon, r.lat) for r in body.rows]
    with cursor() as cur:
        if body.replace:
            cur.execute("DELETE FROM venues WHERE district = %s AND source <> 'osm'", (body.district,))
        psycopg2.extras.execute_values(
            cur, "INSERT INTO venues (district, name, type, fee_mwk, source, geom) VALUES %s", data,
            template="(%s, %s, %s, %s, 'csv', ST_SetSRID(ST_MakePoint(%s, %s), 4326))")
        assign_venue_epas(cur, body.district)
        return {"imported": len(data)}


DISCOVER_SQL = """
INSERT INTO venues (district, name, type, source, osm_id, geom)
SELECT %(district)s, t.name, t.type, 'osm', t.osm_id, ST_SetSRID(ST_MakePoint(t.lon, t.lat), 4326)
FROM unnest(%(ids)s::text[], %(names)s::text[], %(types)s::text[], %(lons)s::float8[], %(lats)s::float8[])
     AS t(osm_id, name, type, lon, lat)
WHERE EXISTS (SELECT 1 FROM farmers f
              WHERE f.district = %(district)s AND f.geom IS NOT NULL AND f.quality = 'ok'
                AND ST_DWithin(f.geom::geography, ST_SetSRID(ST_MakePoint(t.lon, t.lat), 4326)::geography, %(r)s))
ON CONFLICT (district, osm_id) DO UPDATE SET name = EXCLUDED.name, type = EXCLUDED.type
RETURNING type
"""


@app.post("/api/venues/discover")
def discover_venues(body: DiscoverIn):
    """Find schools, cooperatives, halls, markets, churches, clinics and offices in
    OpenStreetMap near this district's farmers, and add them as possible venues."""
    with cursor() as cur:
        cur.execute(
            "SELECT ST_XMin(e)::float8 AS w, ST_YMin(e)::float8 AS s, ST_XMax(e)::float8 AS e, ST_YMax(e)::float8 AS n "
            "FROM (SELECT ST_Envelope(ST_Collect(geom)) AS e FROM farmers "
            "      WHERE district = %s AND geom IS NOT NULL AND quality = 'ok') x", (body.district,))
        box = cur.fetchone()
    if not box or box["w"] is None:
        raise HTTPException(404, f"No mapped farmers in {body.district} yet. Import the Solstice file first.")
    south, west, north, east = osm.padded_bbox(box["w"], box["s"], box["e"], box["n"], body.radius_km)
    if north - south > 1.5 or east - west > 1.5:
        raise HTTPException(400, "The farmers cover too large an area to search at once. Check for wrong coordinates.")
    try:
        found = osm.parse_venues(osm.run_query(osm.venues_query(south, west, north, east)))
    except osm.OverpassError as e:
        raise HTTPException(502, str(e))
    with cursor() as cur:
        cur.execute(DISCOVER_SQL, {
            "district": body.district, "r": body.radius_km * 1000,
            "ids": [v["osm_id"] for v in found], "names": [v["name"] for v in found],
            "types": [v["type"] for v in found], "lons": [v["lon"] for v in found],
            "lats": [v["lat"] for v in found]})
        kept = [r["type"] for r in cur.fetchall()]
        assign_venue_epas(cur, body.district)
    by_type = {}
    for t in kept:
        by_type[t] = by_type.get(t, 0) + 1
    return {"found_in_openstreetmap": len(found), "added_or_updated": len(kept), "by_type": by_type}


# ------------------------------------------------------------------ boundaries
@app.get("/api/boundaries")
def boundaries(district: str = Query(min_length=1)):
    with cursor() as cur:
        cur.execute(
            "SELECT level, name, source, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0005))::json AS geometry "
            "FROM boundaries WHERE district = %s ORDER BY level", (district,))
        rows = cur.fetchall()
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": r["geometry"],
         "properties": {"level": r["level"], "name": r["name"], "source": r["source"]}} for r in rows]}


@app.post("/api/boundaries/fetch")
def fetch_boundary(body: DistrictIn):
    """Download the district outline from OpenStreetMap and keep it in the database."""
    try:
        data = osm.run_query(osm.boundary_query(body.district))
    except osm.OverpassError as e:
        raise HTTPException(502, str(e))
    candidates = osm.relation_wkts(data)
    if not candidates:
        raise HTTPException(404, f"OpenStreetMap has no district outline named '{body.district}'. "
                                 "You can upload one yourself (GeoJSON) instead.")
    best = None
    with cursor() as cur:
        for name, wkt in candidates:
            cur.execute(
                "SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_BuildArea(ST_GeomFromText(%s, 4326))), 3)) AS g",
                (wkt,))
            g = cur.fetchone()["g"]
            if not g:
                continue
            cur.execute("SELECT ST_Area(%s::geography) AS a", (g,))
            area = cur.fetchone()["a"]
            if best is None or area > best[0]:
                best = (area, g, name)
        if best is None:
            raise HTTPException(404, "The outline from OpenStreetMap could not be assembled into a polygon.")
        cur.execute(
            "INSERT INTO boundaries (level, name, district, source, geom) VALUES ('district', %s, %s, 'osm', %s) "
            "ON CONFLICT (level, name, district) DO UPDATE SET geom = EXCLUDED.geom, source = 'osm'",
            (body.district, body.district, best[1]))
    return {"district": body.district, "osm_name": best[2], "area_km2": round(best[0] / 1e6, 1)}


NAME_KEYS = ("name", "NAME", "Name", "EPA", "EPA_NAME", "epa", "epa_name", "NAME_2", "ADM2_EN", "shapeName", "DISTRICT")


@app.post("/api/boundaries/import")
def import_boundaries(body: BoundaryImport):
    """Upload district or EPA polygons (GeoJSON, WGS84 lon/lat), e.g. from the Ministry of Agriculture."""
    feats = [f for f in body.geojson.get("features", []) if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon")]
    if not feats:
        raise HTTPException(422, "No polygons found. Upload a GeoJSON file of district or EPA areas.")

    def fname(f):
        props = f.get("properties") or {}
        if body.name_property and props.get(body.name_property):
            return str(props[body.name_property]).strip()
        return next((str(props[k]).strip() for k in NAME_KEYS if props.get(k)), None)

    wanted = {e.lower() for e in PROJECT.get(body.district, [])}
    with cursor() as cur:
        cur.execute("SELECT DISTINCT epa FROM farmers WHERE district = %s", (body.district,))
        wanted |= {r["epa"].lower() for r in cur.fetchall()}
        keep = []
        for f in feats:
            name = fname(f)
            if not name:
                continue
            short = name.lower().removesuffix(" epa").strip()
            if body.level == "district" and short.removesuffix(" district") == body.district.lower():
                keep.append((body.district, f))
            elif body.level == "epa" and short in wanted:
                keep.append((name.removesuffix(" EPA").removesuffix(" epa").strip().title(), f))
        if not keep:
            names = sorted({n for n in (fname(f) for f in feats) if n})[:15]
            raise HTTPException(422, "None of the areas in the file match " +
                                (body.district if body.level == "district" else f"the EPAs of {body.district}") +
                                ". Names found: " + ", ".join(names))
        import json
        for name, f in keep:
            cur.execute(
                "SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)) AS g",
                (json.dumps(f["geometry"]),))
            g = cur.fetchone()["g"]
            cur.execute("SELECT ST_XMin(%s::geometry) AS x", (g,))
            if abs(cur.fetchone()["x"]) > 180:
                raise HTTPException(422, "The file does not look like lon/lat (WGS84). In QGIS use Export > Save Features As > GeoJSON, CRS EPSG:4326.")
            cur.execute(
                "INSERT INTO boundaries (level, name, district, source, geom) VALUES (%s, %s, %s, 'upload', %s) "
                "ON CONFLICT (level, name, district) DO UPDATE SET geom = EXCLUDED.geom, source = 'upload'",
                (body.level, name, body.district, g))
    return {"imported": [n for n, _ in keep]}


# ------------------------------------------------------------------ the spatial query
EVAL_SQL = """
WITH cand AS (
  SELECT t.idx, ST_SetSRID(ST_MakePoint(t.lon, t.lat), 4326)::geography AS g
  FROM unnest(%(idx)s::int[], %(lons)s::float8[], %(lats)s::float8[]) AS t(idx, lon, lat)
), trips AS (
  -- for every candidate site: the n nearest farmers in scope (KNN on the geography index)
  SELECT c.idx, x.m * %(circ)s / 1000.0 AS road_km
  FROM cand c
  CROSS JOIN LATERAL (
    SELECT ST_Distance(f.geom::geography, c.g) AS m
    FROM farmers f
    WHERE {scope}
    ORDER BY f.geom::geography <-> c.g
    LIMIT %(n)s
  ) x
)
SELECT idx,
       count(*)::int AS farmers,
       sum(CASE WHEN road_km <= %(walk)s THEN 0 ELSE 2 * road_km * %(rate)s END)::float8 AS transport_cost,
       avg(road_km)::float8 AS avg_km,
       max(road_km)::float8 AS max_km,
       (count(*) FILTER (WHERE road_km <= %(walk)s))::int AS walkers
FROM trips GROUP BY idx
"""


def evaluate(cur, scope: Scope, n, cands, p: Params):
    cur.execute(EVAL_SQL.format(scope=scope_sql()), {
        **scope_params(scope),
        "idx": list(range(len(cands))), "lons": [c["lon"] for c in cands], "lats": [c["lat"] for c in cands],
        "circ": p.circuity, "n": n, "walk": p.walk_km, "rate": p.rate_per_km,
    })
    stats = {r["idx"]: r for r in cur.fetchall()}
    out = []
    for i, c in enumerate(cands):
        s = stats[i]
        refreshments = p.refreshment * s["farmers"]
        total = s["transport_cost"] + refreshments + c["fee"]
        out.append({
            **c, "farmers": s["farmers"],
            "transport_cost": round(s["transport_cost"], 2), "refreshments": round(refreshments, 2),
            "venue_fee": round(c["fee"], 2), "total_cost": round(total, 2),
            "per_farmer": round(total / s["farmers"], 2),
            "avg_km": round(s["avg_km"], 2), "max_km": round(s["max_km"], 2), "walkers": s["walkers"],
        })
    return out


@app.post("/api/plan")
def plan(body: PlanIn):
    p = body.params
    with cursor() as cur:
        cur.execute(f"SELECT ST_X(f.geom)::float8 AS lon, ST_Y(f.geom)::float8 AS lat FROM farmers f WHERE {scope_sql()}",
                    scope_params(body))
        homes = cur.fetchall()
        if not homes:
            where = ", ".join(body.epas) + " EPA" if body.epas else body.district
            raise HTTPException(404, f"No mapped farmers found for {where}. Import the Solstice file first.")
        total = len(homes)
        n = min(body.n or total, total)

        types = [norm_type(t) for t in body.venue_types]
        cur.execute(
            "SELECT name, type, epa, source, fee_mwk::float8 AS fee, ST_X(geom)::float8 AS lon, ST_Y(geom)::float8 AS lat "
            "FROM venues WHERE district = %s AND NOT %s AND (cardinality(%s::text[]) = 0 OR type = ANY(%s::text[])) "
            "ORDER BY name",
            (body.district, body.no_venues, types, types))
        cands = [{"name": v["name"], "kind": "venue", "venue_type": v["type"], "venue_epa": v["epa"],
                  "source": v["source"], "fee_known": v["fee"] is not None,
                  "fee": v["fee"] if v["fee"] is not None else p.default_venue_fee,
                  "lon": v["lon"], "lat": v["lat"]} for v in cur.fetchall()]
        n_venues = len(cands)

        lon0, lat0 = sum(h["lon"] for h in homes) / total, sum(h["lat"] for h in homes) / total
        cur.execute(  # measure km per degree here, with PostGIS, so flat-map distances match the database
            "SELECT ST_Distance(ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 4326)::geography, "
            "                   ST_SetSRID(ST_MakePoint(%(x)s + 0.01, %(y)s), 4326)::geography) / 10.0 AS kx, "
            "       ST_Distance(ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 4326)::geography, "
            "                   ST_SetSRID(ST_MakePoint(%(x)s, %(y)s + 0.01), 4326)::geography) / 10.0 AS ky",
            {"x": lon0, "y": lat0})
        scale = cur.fetchone()
        plane = geo.Plane(lon0, lat0, float(scale["kx"]), float(scale["ky"]))
        pts = [plane.xy(h["lon"], h["lat"]) for h in homes]
        venue_xy = [plane.xy(c["lon"], c["lat"]) for c in cands][:40]
        sample = random.Random(42).sample(pts, min(10, total))
        seeds = [(0.0, 0.0)] if n >= total else [(0.0, 0.0)] + venue_xy[:8] + sample[:6]
        cost_seeds = [(0.0, 0.0)] + venue_xy + sample  # the cost search also starts from every venue
        for mode, kind, name in (("cost", "optimal", "Optimal point"), ("fairness", "fairest", "Centre point")):
            xy = geo.ideal_point(pts, n, mode, seeds)
            if mode == "cost" and p.rate_per_km > 0:
                # the real cost has a walk-in cutoff, so refine on the actual cost rule
                xy = geo.best_cost_point(pts, n, p.circuity, p.walk_km, p.rate_per_km, cost_seeds + [xy])
            seeds = seeds + [xy]  # the fairness search also starts from the cost-optimal point
            lon, lat = plane.lonlat(*xy)
            cands.append({"name": name, "kind": kind, "venue_type": None, "venue_epa": None, "source": None,
                          "fee_known": True, "fee": 0.0, "lon": round(lon, 6), "lat": round(lat, 6)})
        for e in body.extra_points:
            cands.append({"name": e.name, "kind": "clicked", "venue_type": None, "venue_epa": None, "source": None,
                          "fee_known": True, "fee": 0.0, "lon": e.lon, "lat": e.lat})
        results = evaluate(cur, body, n, cands, p)

    if body.objective == "cost":
        results.sort(key=lambda r: (r["total_cost"], r["max_km"]))
    else:
        results.sort(key=lambda r: (r["max_km"], r["total_cost"]))
    for i, r in enumerate(results, 1):
        r["rank"] = i
    top = results[:6]
    for r in results[6:]:
        if r["kind"] in ("clicked", "optimal", "fairest"):  # always show the computed and clicked points
            top.append(r)
    if not any(r["kind"] == "venue" for r in top):  # always show the best real venue
        best_venue = next((r for r in results if r["kind"] == "venue"), None)
        if best_venue:
            top.append(best_venue)
    return {"district": body.district, "farmers_total": total, "n_used": n, "venues_considered": n_venues,
            "objective": body.objective, "candidates": top}


@app.post("/api/cohort")
def cohort(body: CohortIn):
    """The n farmers closest to a chosen site, with each one's trip and cost."""
    p = body.params
    point = "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography"
    with cursor() as cur:
        cur.execute(
            "SELECT f.id, f.serial, f.name, f.sex, f.phone, f.epa, f.ward, f.village, "
            "       ST_X(f.geom)::float8 AS lon, ST_Y(f.geom)::float8 AS lat, "
            f"       ST_Distance(f.geom::geography, {point}) / 1000.0 AS straight_km "
            f"FROM farmers f WHERE {scope_sql()} "
            f"ORDER BY f.geom::geography <-> {point} LIMIT %(n)s",
            {**scope_params(body), "lon": body.lon, "lat": body.lat, "n": body.n})
        rows = cur.fetchall()
    if not rows:
        raise HTTPException(404, "No farmers found.")

    bands = [0] * (len(BAND_EDGES_KM) + 1)
    transport, walkers = 0.0, 0
    by_epa = {}
    for r in rows:
        road = r.pop("straight_km") * p.circuity
        walks = road <= p.walk_km
        cost = 0.0 if walks else 2 * road * p.rate_per_km
        r.update(road_km=round(road, 2), walks=walks, transport_cost=round(cost, 2),
                 band=bisect.bisect_left(BAND_EDGES_KM, road))
        bands[r["band"]] += 1
        transport += cost
        walkers += walks
        by_epa[r["epa"]] = by_epa.get(r["epa"], 0) + 1
    n = len(rows)
    refreshments = p.refreshment * n
    total = transport + refreshments + body.fee
    return {
        "summary": {
            "farmers": n, "transport_cost": round(transport, 2), "refreshments": round(refreshments, 2),
            "venue_fee": round(body.fee, 2), "total_cost": round(total, 2), "per_farmer": round(total / n, 2),
            "avg_km": round(sum(r["road_km"] for r in rows) / n, 2), "max_km": max(r["road_km"] for r in rows),
            "walkers": walkers, "women": sum(1 for r in rows if r["sex"] == "Female"),
            "with_phone": sum(1 for r in rows if r["phone"]),
        },
        "by_epa": by_epa, "bands": bands, "attendees": rows,
    }


# ------------------------------------------------------------------ scenarios
@app.post("/api/scenarios", status_code=201)
def save_scenario(s: ScenarioIn):
    params = s.params.model_dump()
    params["epas"] = s.epas
    with cursor() as cur:
        cur.execute(
            "INSERT INTO scenarios (district, n_farmers, objective, site_name, site, total_cost, avg_km, max_km, params) "
            "VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s) RETURNING id",
            (s.district, s.n_farmers, s.objective, s.site_name, s.lon, s.lat,
             s.total_cost, s.avg_km, s.max_km, psycopg2.extras.Json(params)))
        return {"id": cur.fetchone()["id"]}


@app.get("/api/scenarios")
def list_scenarios(district: str = Query(min_length=1)):
    with cursor() as cur:
        cur.execute(
            "SELECT id, created_at, n_farmers, objective, site_name, params->'epas' AS epas, "
            "ST_X(site)::float8 AS lon, ST_Y(site)::float8 AS lat, "
            "total_cost::float8 AS total_cost, avg_km::float8 AS avg_km, max_km::float8 AS max_km "
            "FROM scenarios WHERE district = %s ORDER BY id DESC LIMIT 20", (district,))
        return cur.fetchall()


@app.delete("/api/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int):
    with cursor() as cur:
        cur.execute("DELETE FROM scenarios WHERE id = %s", (scenario_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Scenario not found")


# Static front end last, so it doesn't shadow /api
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
