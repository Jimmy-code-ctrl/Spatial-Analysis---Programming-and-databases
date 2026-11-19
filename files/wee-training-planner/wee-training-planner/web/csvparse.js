"use strict";
/* Reads a pasted or uploaded venue list (CSV / TSV / semicolon).
   Columns: name, lat, lon, then optional type and fee (MWK).
   A header row is detected automatically and the column order may vary. */
(function (root) {
  const ALIAS = {
    lat: ["lat", "latitude", "y"],
    lon: ["lon", "lng", "long", "longitude", "x"],
    name: ["name", "venue", "place"],
    type: ["type", "kind", "category"],
    fee: ["fee", "cost", "fee_mwk", "price"],
  };
  const ALL = new Set(Object.values(ALIAS).flat());
  const TYPES = ["primary_school", "secondary_school", "school", "cooperative", "community_hall",
    "worship", "market", "health_centre", "extension_office", "other"];
  const SYNONYMS = { church: "worship", mosque: "worship", hall: "community_hall", clinic: "health_centre",
    hospital: "health_centre", admarc: "market", "co-operative": "cooperative", coop: "cooperative" };

  function detectDelimiter(line) {
    const counts = { "\t": 0, ";": 0, ",": 0 };
    let quoted = false;
    for (const ch of line) {
      if (ch === '"') quoted = !quoted;
      else if (!quoted && ch in counts) counts[ch]++;
    }
    const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    return best[1] > 0 ? best[0] : ",";
  }

  function splitLine(line, delim) {
    const out = [];
    let cur = "", quoted = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (quoted && line[i + 1] === '"') { cur += '"'; i++; } else quoted = !quoted;
      } else if (ch === delim && !quoted) { out.push(cur.trim()); cur = ""; }
      else cur += ch;
    }
    out.push(cur.trim());
    return out;
  }

  function toNum(s, delim) {
    if (s == null) return NaN;
    let t = String(s).trim();
    if (t === "") return NaN;
    if (delim !== ",") t = t.replace(",", ".");
    return Number(t);
  }

  function parseVenues(text) {
    const lines = String(text).replace(/\r/g, "").split("\n")
      .map((l, i) => ({ text: l.trim(), line: i + 1 })).filter((l) => l.text);
    const res = { rows: [], rejected: [] };
    if (!lines.length) return res;
    const delim = detectDelimiter(lines[0].text);
    const table = lines.map((l) => ({ line: l.line, cols: splitLine(l.text, delim) }));
    const first = table[0].cols.map((c) => c.toLowerCase());
    const header = first.some((c) => ALL.has(c)) ? first : null;
    const find = (f) => (header ? header.findIndex((h) => ALIAS[f].includes(h)) : -1);
    const idx = header
      ? { name: find("name"), lat: find("lat"), lon: find("lon"), type: find("type"), fee: find("fee") }
      : { name: 0, lat: 1, lon: 2, type: 3, fee: 4 };

    for (const r of header ? table.slice(1) : table) {
      if (idx.name < 0 || idx.lat < 0 || idx.lon < 0) {
        res.rejected.push({ line: r.line, reason: "Header needs name, lat and lon columns" });
        continue;
      }
      const name = r.cols[idx.name];
      const lat = toNum(r.cols[idx.lat], delim), lon = toNum(r.cols[idx.lon], delim);
      const feeRaw = idx.fee >= 0 ? r.cols[idx.fee] : "";
      const fee = feeRaw === undefined || feeRaw === "" ? null : toNum(feeRaw, delim);
      let type = idx.type >= 0 ? String(r.cols[idx.type] || "other").toLowerCase().trim().replace(/\s+/g, "_") : "other";
      type = SYNONYMS[type] || type;
      if (!TYPES.includes(type)) type = "other";
      if (!name) { res.rejected.push({ line: r.line, reason: "Missing venue name" }); continue; }
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) { res.rejected.push({ line: r.line, reason: "Latitude or longitude is not a number" }); continue; }
      if (Math.abs(lat) > 90 || Math.abs(lon) > 180) { res.rejected.push({ line: r.line, reason: "Coordinates out of range" }); continue; }
      if (fee !== null && (!Number.isFinite(fee) || fee < 0)) { res.rejected.push({ line: r.line, reason: "Fee must be a non-negative number" }); continue; }
      res.rows.push({ name, type, fee, lat, lon });
    }
    return res;
  }

  root.CsvParse = { parseVenues };
  if (typeof module !== "undefined" && module.exports) module.exports = root.CsvParse;
})(typeof window !== "undefined" ? window : globalThis);
