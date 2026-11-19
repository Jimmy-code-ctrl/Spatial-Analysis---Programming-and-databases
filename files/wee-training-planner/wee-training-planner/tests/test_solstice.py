"""Unit tests for the Solstice reader (no database needed).

Run from the project folder:   python -m unittest discover -s tests -v
"""
import io
import sys
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
import solstice  # noqa: E402

HEAD = ["Country of Implementation", "Country and Operational Area", "Ward", "Rightsholder  first Name", "Surname",
        "Sex", "Village /Plot /Farm name", "Phone number", "Serial Number",
        "GPS Coordinates (Location Answered) (latitude)", "GPS Coordinates (Location Answered) (longitude)",
        "GPS Coordinates (Location Answered - accuracy)",
        "Household Size (Location Answered) (latitude)", "Household Size (Location Answered) (longitude)"]


def workbook(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(HEAD)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def row(area="Malawi and Chipoka EPA - Salima", serial=1, gps=(-13.97, 34.50), hh=(None, None), **kw):
    return ["Malawi", area, kw.get("ward", "ngodzi"), kw.get("first", "amina"), kw.get("sur", "phiri"),
            kw.get("sex", "Female"), "Kapeni", kw.get("phone", 998288013), serial, gps[0], gps[1], 6.0, hh[0], hh[1]]


class SolsticeTests(unittest.TestCase):
    def test_area_string_split_and_fuzzy_names(self):
        self.assertEqual(solstice.parse_area("Malawi and Chipoka EPA - Salima"), ("Malawi", "Chipoka", "Salima"))
        self.assertEqual(solstice.parse_area("Malawi and  Chigulukwe  EPA -  Salima")[1:], ("Chigulukwe", "Salima"))
        self.assertIsNone(solstice.parse_area("nonsense"))
        self.assertEqual(solstice.snap("Mangoch", solstice.KNOWN_DISTRICTS), ("Mangochi", "Mangoch"))
        self.assertEqual(solstice.snap("salima", solstice.KNOWN_DISTRICTS)[0], "Salima")
        self.assertEqual(solstice.snap("Kasungu", solstice.KNOWN_DISTRICTS)[0], "Kasungu")  # unknown names kept

    def test_phone_numbers(self):
        self.assertEqual(solstice.clean_phone(998288013), "0998288013")
        self.assertEqual(solstice.clean_phone(265997355361), "+265997355361")
        self.assertEqual(solstice.clean_phone("0888 123 456"), "0888123456")
        self.assertIsNone(solstice.clean_phone(None))

    def test_gps_first_then_household_then_none(self):
        data = workbook([row(serial=1), row(serial=2, gps=(None, None), hh=(-13.9, 34.4)), row(serial=3, gps=(None, None))])
        p = solstice.parse(data, "x.xlsx")
        self.assertEqual(p.sources, {"gps": 1, "household": 1, "phase1": 0, "none": 1})
        by = {r["serial"]: r for r in p.records}
        self.assertEqual(by["1"]["coord_source"], "gps")
        self.assertEqual(by["2"]["wkt"], "POINT(34.4 -13.9)")
        self.assertIsNone(by["3"]["wkt"])

    def test_bad_coordinates_are_skipped(self):
        data = workbook([row(serial=1, gps=(0, 0)), row(serial=2, gps=(95, 34)), row(serial=3, gps=("abc", 34))])
        self.assertEqual(solstice.parse(data, "x.xlsx").sources["none"], 3)

    def test_text_is_tidied_and_duplicates_merged(self):
        data = workbook([row(serial=7, ward="  lifidzi ", first="JOHN", sur="banda"), row(serial=7)])
        p = solstice.parse(data, "x.xlsx")
        self.assertEqual(p.duplicates, 1)
        self.assertEqual(len(p.records), 1)
        r = p.records[0]
        self.assertEqual((r["ward"], r["name"], r["sex"]), ("Ngodzi", "Amina Phiri", "Female"))  # last row wins

    def test_rows_without_a_readable_area_are_rejected(self):
        p = solstice.parse(workbook([row(serial=1), row(area="garbage", serial=2)]), "x.xlsx")
        self.assertEqual(len(p.records), 1)
        self.assertEqual(len(p.rejected), 1)

    def test_clear_errors_for_wrong_files(self):
        with self.assertRaises(solstice.ImportProblem):
            solstice.parse(b"%PDF-1.4", "notes.pdf")
        with self.assertRaises(solstice.ImportProblem):
            solstice.parse(b"not a zip", "x.xlsx")
        wb = Workbook(); wb.active.append(["a", "b"]); buf = io.BytesIO(); wb.save(buf)
        with self.assertRaises(solstice.ImportProblem):
            solstice.parse(buf.getvalue(), "x.xlsx")

    def test_csv_export_also_works(self):
        csv_text = ",".join(HEAD) + "\nMalawi,Malawi and Rivirivi EPA - Balaka,x,a,b,Male,v,0999111222,5,-14.9,35.0,3,,\n"
        p = solstice.parse(csv_text.encode(), "x.csv")
        self.assertEqual((p.records[0]["district"], p.records[0]["epa"], p.records[0]["sex"]), ("Balaka", "Rivirivi", "Male"))

    def test_bundled_sample_file(self):
        p = solstice.parse((ROOT / "data" / "sample_solstice_export.xlsx").read_bytes(), "sample.xlsx")
        self.assertEqual(p.rows_read, 870)
        self.assertEqual({(r["district"], r["epa"]) for r in p.records},
                         {("Salima", "Chipoka"), ("Salima", "Chigulukwe"), ("Mangochi", "Nankumba"), ("Balaka", "Rivirivi")})
        self.assertEqual(p.corrections, {"Mangoch": "Mangochi"})


if __name__ == "__main__":
    unittest.main()
