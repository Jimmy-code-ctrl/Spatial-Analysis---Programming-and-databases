-- Training Site Planner: schema
-- Geometry is stored as EPSG:4326 (lon/lat). Distances use the geography type,
-- so results are in metres without projecting the data.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Beneficiaries imported from a Solstice export (WEECVC cotton project).
CREATE TABLE farmers (
    id          serial PRIMARY KEY,
    district    text NOT NULL,
    epa         text NOT NULL,
    ward        text,
    village     text,
    serial      text NOT NULL,              -- Solstice "Serial Number"
    name        text,
    sex         text,
    phone       text,
    category    text,                       -- scale of operations
    value_chain text,
    coord_source text,                      -- gps | household | phase1 | NULL
    accuracy_m  real,
    quality     text NOT NULL DEFAULT 'ok' CHECK (quality IN ('ok', 'outlier', 'missing')),
    geom        geometry(Point, 4326),      -- NULL when the export has no coordinates
    imported_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (district, epa, serial)
);

-- Possible meeting places: schools, cooperatives, halls, churches, markets...
CREATE TABLE venues (
    id       serial PRIMARY KEY,
    district text NOT NULL,
    epa      text,                          -- nearest farmers' EPA, filled automatically
    name     text NOT NULL,
    type     text NOT NULL DEFAULT 'other',
    fee_mwk  numeric(12, 2) CHECK (fee_mwk >= 0),   -- NULL = unknown, planner uses a default
    source   text NOT NULL DEFAULT 'manual',        -- osm | csv | manual
    osm_id   text,
    geom     geometry(Point, 4326) NOT NULL,
    UNIQUE (district, osm_id)
);

-- District and EPA boundaries (district from OpenStreetMap, EPA from an uploaded file).
CREATE TABLE boundaries (
    id       serial PRIMARY KEY,
    level    text NOT NULL CHECK (level IN ('district', 'epa')),
    name     text NOT NULL,
    district text NOT NULL,
    source   text NOT NULL,
    geom     geometry(MultiPolygon, 4326) NOT NULL,
    UNIQUE (level, name, district)
);

-- Saved planning runs, so options can be compared later.
CREATE TABLE scenarios (
    id         serial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    district   text NOT NULL,
    n_farmers  integer NOT NULL,
    objective  text NOT NULL,
    site_name  text NOT NULL,
    site       geometry(Point, 4326) NOT NULL,
    total_cost numeric(14, 2) NOT NULL,
    avg_km     numeric(8, 2) NOT NULL,
    max_km     numeric(8, 2) NOT NULL,
    params     jsonb NOT NULL
);

CREATE INDEX farmers_area_ix    ON farmers (district, epa);
CREATE INDEX farmers_geog_gix   ON farmers USING gist ((geom::geography));
CREATE INDEX venues_district_ix ON venues (district);
CREATE INDEX venues_geom_gix    ON venues USING gist (geom);
CREATE INDEX boundaries_geom_gix ON boundaries USING gist (geom);
