// Run with:  node tests/test_csvparse.js
const assert = require("assert");
const path = require("path");
const P = require(path.join(__dirname, "..", "web", "csvparse.js"));

let v = P.parseVenues("name,type,lat,lon,fee\nMtunthama Primary,primary_school,-13.96,34.50,0\nSt Mary church,Church,-13.97,34.51,500");
assert.strictEqual(v.rows.length, 2);
assert.strictEqual(v.rows[1].type, "worship", "church maps to worship");
assert.strictEqual(v.rows[1].fee, 500);
assert.strictEqual(v.rows[0].fee, 0);

v = P.parseVenues("Hall A,-13.9,33.7\nHall B,-13.8,33.6,hall,");                      // no header, optional columns
assert.strictEqual(v.rows.length, 2); assert.strictEqual(v.rows[1].type, "community_hall"); assert.strictEqual(v.rows[1].fee, null);

v = P.parseVenues("lat,lon,name\n-13.9,33.7,Order Test");                              // header in other order
assert.strictEqual(v.rows[0].name, "Order Test"); assert.strictEqual(v.rows[0].lat, -13.9);

v = P.parseVenues("name;lat;lon;fee\nKasungu Coop;-13,02;33,48;2500");                // semicolons and decimal commas
assert.strictEqual(v.rows[0].lat, -13.02); assert.strictEqual(v.rows[0].fee, 2500);

v = P.parseVenues('name,lat,lon\n"Phiri, Hall",-13.9,33.7\nBad,abc,33\nFar,-99,33\n,-13,33\n');
assert.strictEqual(v.rows.length, 1); assert.strictEqual(v.rows[0].name, "Phiri, Hall");
assert.strictEqual(v.rejected.length, 3); assert.strictEqual(v.rejected[0].line, 3);

v = P.parseVenues("name,lat,lon,fee\nHall,-13.9,33.7,-5");
assert.strictEqual(v.rejected.length, 1);
assert.strictEqual(P.parseVenues("").rows.length, 0);
assert.strictEqual(P.parseVenues("name,type\nA,school").rejected.length, 1);            // header without coordinates

v = P.parseVenues("name,type,lat,lon\nX,Admarc,-13.9,33.7\nY,unknown thing,-13.9,33.7");
assert.strictEqual(v.rows[0].type, "market"); assert.strictEqual(v.rows[1].type, "other");
console.log("venue CSV parser: all tests passed");
