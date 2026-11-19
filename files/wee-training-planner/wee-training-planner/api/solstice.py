"""Reader for Solstice beneficiary exports (.xlsx or .csv) from the WEECVC cotton project.

Only the fields the planner needs are kept. Date of birth, disability status,
household composition, livestock and similar columns are deliberately ignored.
"""
import csv
import difflib
import io
import re
from dataclasses import dataclass, field

from openpyxl import load_workbook

KNOWN_DISTRICTS = ["Salima", "Mangochi", "Balaka"]
KNOWN_EPAS = ["Chipoka", "Chigulukwe", "Nankumba", "Rivirivi"]

AREA_RE = re.compile(
    r"^\s*(?P<country>.+?)\s+and\s+(?P<epa>.+?)(?:\s+EPA)?\s*[-\u2013\u2014]\s*(?P<district>.+?)\s*$",
    re.IGNORECASE,
)


class ImportProblem(Exception):
    """The file cannot be read as a Solstice export (message is shown to the user)."""


@dataclass
class Parsed:
    records: list = field(default_factory=list)
    rejected: list = field(default_factory=list)      # [(row_number, reason)]
    corrections: dict = field(default_factory=dict)   # {"Mangoch": "Mangochi"}
    sources: dict = field(default_factory=lambda: {"gps": 0, "household": 0, "phase1": 0, "none": 0})
    duplicates: int = 0
    rows_read: int = 0
    non_malawi: int = 0
    warnings: list = field(default_factory=list)


def norm(h):
    return re.sub(r"\s+", " ", str(h if h is not None else "")).strip().lower()


def clean_text(v, title=False):
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    if not s or s.lower() in ("nan", "none", "n/a"):
        return None
    return s.title() if title else s


def to_float(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(str(v).strip().replace(",", ".")) if isinstance(v, str) else float(v)
    except ValueError:
        return None
    return f if f == f else None


def clean_phone(v):
    """998288013 -> 0998288013 ; 265997355361 -> +265997355361 ; leaves odd values as digits."""
    if v is None:
        return None
    digits = re.sub(r"\D", "", str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
    if not digits:
        return None
    if digits.startswith("265") and len(digits) == 12:
        return "+" + digits
    if len(digits) == 9:
        return "0" + digits
    return digits


def clean_sex(v):
    s = norm(v)
    if s in ("female", "f", "woman"):
        return "Female"
    if s in ("male", "m", "man"):
        return "Male"
    return None


def snap(value, known):
    """Tidy a place name and correct near-misses against the project's known names."""
    v = clean_text(value, title=True)
    if not v:
        return None, None
    match = difflib.get_close_matches(v.lower(), [k.lower() for k in known], n=1, cutoff=0.8)
    if match:
        fixed = next(k for k in known if k.lower() == match[0])
        return fixed, (v if fixed != v else None)
    return v, None


def read_table(data: bytes, filename: str):
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # corrupt or not really an xlsx
            raise ImportProblem(f"Could not open the Excel file ({e.__class__.__name__}). Re-export it from Solstice.")
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if header and any(norm(c) == "country and operational area" for c in header):
                body = [list(r) for r in rows if any(c not in (None, "") for c in r)]
                return list(header), body
        raise ImportProblem("No sheet has a 'Country and Operational Area' column. Is this a Solstice beneficiary export?")
    if name.endswith((".csv", ".txt")):
        text = data.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            raise ImportProblem("The CSV file is empty.")
        return rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]
    raise ImportProblem("Please upload the Solstice export as .xlsx (or .csv).")


def build_columns(header):
    h = [norm(x) for x in header]

    def exact(*names):
        for n in names:
            if n in h:
                return h.index(n)
        return None

    def having(*parts):
        for i, x in enumerate(h):
            if all(p in x for p in parts):
                return i
        return None

    cols = {
        "area": exact("country and operational area"),
        "country": exact("country of implementation"),
        "ward": exact("ward"),
        "first": having("first name"),
        "surname": exact("surname"),
        "sex": exact("sex"),
        "village": having("village"),
        "phone": exact("phone number"),
        "category": having("rightsholder category"),
        "value_chain": exact("value chain"),
        "serial": exact("serial number"),
        "response": exact("response code"),
    }
    coords = []
    for key, tag in (("gps", "gps coordinates"), ("household", "household size"), ("phase1", "phase 1")):
        lat, lon = having(tag, "latitude"), having(tag, "longitude")
        if lat is not None and lon is not None:
            coords.append((key, lat, lon, having(tag, "accuracy")))
    cols["coords"] = coords

    missing = []
    if cols["area"] is None:
        missing.append("Country and Operational Area")
    if cols["serial"] is None and cols["response"] is None:
        missing.append("Serial Number")
    if not coords:
        missing.append("GPS Coordinates (latitude/longitude)")
    if missing:
        raise ImportProblem("The file is missing expected Solstice columns: " + ", ".join(missing) + ".")
    return cols


def parse_area(text):
    m = AREA_RE.match(str(text or ""))
    if not m:
        return None
    return m.group("country").strip(), m.group("epa").strip(), m.group("district").strip()


def pick_coordinates(row, cols):
    """GPS first, then the household-size capture, then the phase 1 capture."""
    for key, i_lat, i_lon, i_acc in cols["coords"]:
        lat = to_float(row[i_lat]) if i_lat < len(row) else None
        lon = to_float(row[i_lon]) if i_lon < len(row) else None
        if lat is None or lon is None:
            continue
        if abs(lat) > 90 or abs(lon) > 180 or (abs(lat) < 0.5 and abs(lon) < 0.5):
            continue
        acc = to_float(row[i_acc]) if i_acc is not None and i_acc < len(row) else None
        return key, lat, lon, acc
    return None, None, None, None


def parse(data: bytes, filename: str) -> Parsed:
    header, body = read_table(data, filename)
    cols = build_columns(header)
    out = Parsed()
    seen = {}

    def cell(row, key):
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else None

    for n, row in enumerate(body, start=2):
        out.rows_read += 1
        area = parse_area(cell(row, "area"))
        if not area:
            out.rejected.append((n, f"Could not read the EPA and district from '{cell(row, 'area')}'"))
            continue
        country, epa_raw, district_raw = area
        district, d_fix = snap(district_raw, KNOWN_DISTRICTS)
        epa, e_fix = snap(epa_raw, KNOWN_EPAS)
        for raw, fixed in ((d_fix, district), (e_fix, epa)):
            if raw:
                out.corrections[raw] = fixed
        if norm(cell(row, "country")) not in ("", "malawi"):
            out.non_malawi += 1

        serial = clean_text(cell(row, "serial")) or clean_text(cell(row, "response"))
        if not serial:
            out.rejected.append((n, "No serial number"))
            continue
        first, surname = clean_text(cell(row, "first"), True), clean_text(cell(row, "surname"), True)
        source, lat, lon, acc = pick_coordinates(row, cols)
        out.sources[source or "none"] += 1
        rec = {
            "district": district, "epa": epa, "serial": serial,
            "ward": clean_text(cell(row, "ward"), True), "village": clean_text(cell(row, "village"), True),
            "name": " ".join(x for x in (first, surname) if x) or None,
            "sex": clean_sex(cell(row, "sex")), "phone": clean_phone(cell(row, "phone")),
            "category": clean_text(cell(row, "category")), "value_chain": clean_text(cell(row, "value_chain")),
            "coord_source": source, "accuracy_m": acc,
            "wkt": f"POINT({lon} {lat})" if source else None,
        }
        key = (district, epa, serial)
        if key in seen:
            out.duplicates += 1
        seen[key] = rec  # last one wins
    out.records = list(seen.values())
    if not out.records:
        raise ImportProblem("No usable rows were found. " + (out.rejected[0][1] if out.rejected else ""))
    if out.non_malawi:
        out.warnings.append(f"{out.non_malawi} rows list a country other than Malawi. They were still imported under their EPA.")
    return out
