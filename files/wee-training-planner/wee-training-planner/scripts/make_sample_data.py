#!/usr/bin/env python3
"""Generate a SYNTHETIC Solstice-format export for demos (no real people).

    python scripts/make_sample_data.py

Writes data/sample_solstice_export.xlsx with the same column headers as the real
WEECVC export, covering all four project EPAs (Chipoka and Chigulukwe in Salima,
Nankumba in Mangochi, Rivirivi in Balaka). Names, phone numbers and locations are
invented: EPA centres are only approximate. It deliberately includes some missing
coordinates, a few wrong ones and some untidy spellings, so the importer's data
checks have something to show.

Never put the real beneficiary export in the Git repository.
"""
import random
from pathlib import Path

from openpyxl import Workbook

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_solstice_export.xlsx"

HEADERS = [
    "Response Code",
    "Submitted On",
    "Country of Implementation",
    "Partner Organisation",
    "Country and Operational Area",
    "Country and Operational Area (Other (please specify)) - specify",
    "Ward",
    "Rightsholder  first Name",
    "Surname",
    "Nationally assigned number",
    "Nationally assigned number (Not Applicable)",
    "Nationally assigned number (Don't Know)",
    "Rightsholder Category (scale of operations)",
    "Where you a beneficiary under phase 1 of the cotton project?",
    "Where you a beneficiary under phase 1 of the cotton project? (Location Answered) (latitude)",
    "Where you a beneficiary under phase 1 of the cotton project? (Location Answered) (longitude)",
    "Where you a beneficiary under phase 1 of the cotton project? (Location Answered - accuracy)",
    "Where you a beneficiary under phase 1 of the cotton project? (Location Answered - altitude)",
    "Value Chain",
    "Value Chain (Cotton and another (please specify)) - specify",
    "Value Chain (Other (please specify)) - specify",
    "Rightsholder has smartphone",
    "Phone number",
    "Phone number (Not Applicable)",
    "Sex",
    "Village /Plot /Farm name",
    "GPS Coordinates",
    "GPS Coordinates (Location Answered) (latitude)",
    "GPS Coordinates (Location Answered) (longitude)",
    "GPS Coordinates (Location Answered - accuracy)",
    "GPS Coordinates (Location Answered - altitude)",
    "GPS Coordinates (Not Applicable)",
    "Disability Status",
    "Date of birth",
    "Date of birth (Not Applicable)",
    "Date of birth (Don't Know)",
    "Age",
    "Marital status ",
    "Household Size: Female - <2 years",
    "Household Size: Female - 2-5 years",
    "Household Size: Female - 6-17 years",
    "Household Size: Female - 18- 35years",
    "Household Size: Female - 36 - 60+ years",
    "Household Size: Male - <2 years",
    "Household Size: Male - 2-5 years",
    "Household Size: Male - 6-17 years",
    "Household Size: Male - 18- 35years",
    "Household Size: Male - 36 - 60+ years",
    "Household Size (Location Answered) (latitude)",
    "Household Size (Location Answered) (longitude)",
    "Household Size (Location Answered - accuracy)",
    "Household Size (Location Answered - altitude)",
    "Do you belong to any of these Cotton Value Chain categories?: Study circle group - undefined",
    "Do you belong to any of these Cotton Value Chain categories?: Saving Group - undefined",
    "Do you belong to any of these Cotton Value Chain categories?: Producer Group - undefined",
    "Do you belong to any of these Cotton Value Chain categories?: Processors Group - undefined",
    "Do you belong to any of these Cotton Value Chain categories?: Marketing Group - undefined",
    "Do you belong to any of these Cotton Value Chain categories?: Other (Specify) - undefined",
    "Do you belong to any of these Cotton Value Chain categories? (Comments)",
    "Land size: Cotton farmed - undefined",
    "Land size: Arable - undefined",
    "Land size: Non Arable - undefined",
    "Livestock owned by rightsholder: Cattle - Status",
    "Livestock owned by rightsholder: Cattle - Number of livestock",
    "Livestock owned by rightsholder: Cattle - If yes what is the main reason for keeping the livestock",
    "Livestock owned by rightsholder: Goats - Status",
    "Livestock owned by rightsholder: Goats - Number of livestock",
    "Livestock owned by rightsholder: Goats - If yes what is the main reason for keeping the livestock",
    "Livestock owned by rightsholder: Poultry (chickens, guines fowls, ducks, etc) - Status",
    "Livestock owned by rightsholder: Poultry (chickens, guines fowls, ducks, etc) - Number of livestock",
    "Livestock owned by rightsholder: Poultry (chickens, guines fowls, ducks, etc) - If yes what is the main reason for keeping the livestock",
    "Livestock owned by rightsholder: Pigs - Status",
    "Livestock owned by rightsholder: Pigs - Number of livestock",
    "Livestock owned by rightsholder: Pigs - If yes what is the main reason for keeping the livestock",
    "Livestock owned by rightsholder: Draught animals (donkeys, mules, horses) - Status",
    "Livestock owned by rightsholder: Draught animals (donkeys, mules, horses) - Number of livestock",
    "Livestock owned by rightsholder: Draught animals (donkeys, mules, horses) - If yes what is the main reason for keeping the livestock",
    "Livestock owned by rightsholder: Other (specify) - Status",
    "Livestock owned by rightsholder: Other (specify) - Number of livestock",
    "Livestock owned by rightsholder: Other (specify) - If yes what is the main reason for keeping the livestock",
    "Livestock owned by rightsholder (Comments)",
    "Serial Number",
    "UIC",
    "Beneficiary ID"
]

# EPA, district, centre lat, centre lon, farmers (approximate centres, demo only)
AREAS = [
    ("Chipoka", "Salima", -13.98, 34.50, 260),
    ("Chigulukwe", "Salima", -13.66, 34.40, 190),
    ("Nankumba", "Mangochi", -14.06, 34.86, 220),
    ("Rivirivi", "Balaka", -15.06, 35.08, 200),
]
WARDS = {"Chipoka": ["Ngodzi", "Lifidzi", "Chipoka"], "Chigulukwe": ["Chigulukwe", "Kaphatenga", "Tembwe"],
         "Nankumba": ["Nankumba", "Chembe", "Mvunguti"], "Rivirivi": ["Rivirivi", "Chiyendausiku", "Nsamala"]}
CATEGORIES = ["Smallholder", "Smallholder", "Smallholder", "Commercial"]


def col(name):
    return HEADERS.index(name)


def main():
    rnd = random.Random(2026)
    wb = Workbook()
    ws = wb.active
    ws.title = "Beneficiaries"
    ws.append(HEADERS)
    serial = 1000
    i_area, i_country = col("Country and Operational Area"), col("Country of Implementation")
    i_ward, i_vil = col("Ward"), col("Village /Plot /Farm name")
    i_first, i_sur = col("Rightsholder  first Name"), col("Surname")
    i_sex, i_phone = col("Sex"), col("Phone number")
    i_cat, i_serial = col("Rightsholder Category (scale of operations)"), col("Serial Number")
    g_lat = col("GPS Coordinates (Location Answered) (latitude)")
    g_lon = col("GPS Coordinates (Location Answered) (longitude)")
    g_acc = col("GPS Coordinates (Location Answered - accuracy)")
    h_lat = col("Household Size (Location Answered) (latitude)")
    h_lon = col("Household Size (Location Answered) (longitude)")

    for epa, district, clat, clon, count in AREAS:
        villages = [(f"Village {k + 1}", clat + rnd.uniform(-0.12, 0.12), clon + rnd.uniform(-0.13, 0.13))
                    for k in range(8)]
        weights = [rnd.uniform(0.5, 2.0) for _ in villages]
        for k in range(count):
            serial += 1
            v = rnd.choices(villages, weights)[0]
            row = [None] * len(HEADERS)
            district_text = "Mangoch" if (district == "Mangochi" and k % 7 == 0) else district  # untidy spelling
            row[i_area] = f"Malawi and {epa} EPA - {district_text}"
            row[i_country] = "Malawi"
            ward = rnd.choice(WARDS[epa])
            row[i_ward] = ward.lower() if k % 11 == 0 else ward   # untidy capitalisation
            row[i_vil] = v[0]
            row[i_first], row[i_sur] = "Demo", f"Farmer {epa[:3].upper()}-{k + 1:03d}"
            row[i_sex] = "Female" if rnd.random() < 0.6 else "Male"
            row[i_phone] = 990000000 + serial if rnd.random() < 0.3 else None   # invented numbers
            row[i_cat] = rnd.choice(CATEGORIES)
            row[i_serial] = serial
            lat, lon = round(v[1] + rnd.gauss(0, 0.012), 7), round(v[2] + rnd.gauss(0, 0.012), 7)
            roll = rnd.random()
            if roll < 0.22:
                pass                                     # no coordinates captured
            elif roll < 0.27:
                row[h_lat], row[h_lon] = lat, lon        # only the household-size location
            elif roll < 0.30:
                row[g_lat], row[g_lon], row[g_acc] = lat + 0.35, lon - 0.3, 5.0   # a wrong GPS fix, far away
            else:
                row[g_lat], row[g_lon], row[g_acc] = lat, lon, round(rnd.uniform(2, 12), 2)
            ws.append(row)
    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    print("Wrote", OUT, "with", serial - 1000, "synthetic rows")


if __name__ == "__main__":
    main()
