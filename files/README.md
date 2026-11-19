# Training Site Planner

A web app for the **WEECVC cotton project**. It reads your Solstice beneficiary export and answers one practical question:

> **Where should we hold a farmer training, and what will it cost to get the farmers there?**

You choose a district (Salima, Mangochi or Balaka), the EPAs to invite from, and how many farmers you want. The app then:

- maps every farmer's home, and flags GPS points that look wrong,
- draws each EPA's area on the district map,
- finds possible venues (primary schools, cooperatives, halls, churches, markets, health centres, extension offices) from OpenStreetMap, or from your own list,
- works out which farmers are nearest each venue, how far they travel and what mobilising them will cost,
- recommends the most convenient meeting place and gives you the attendee list to download.

Built for the GIS assignment *Practical V: Spatial Analysis, Programming and Databases*.

> **Important:** the sample data in this project is **synthetic** (invented names, phone numbers and locations). Your real Solstice export contains personal information. Keep it on your own computer and **never add it to the Git repository** (see [Part 7](#7-publish-the-project-on-github-for-the-assignment)).

---

## Contents

1. [Install Docker (once)](#1-install-docker-once)
2. [Get the project ready](#2-get-the-project-ready)
3. [Start the app](#3-start-the-app)
4. [Use the app](#4-use-the-app)
5. [Stop it, start it again, reset it](#5-stop-it-start-it-again-reset-it)
6. [Something went wrong?](#6-something-went-wrong)
7. [Publish the project on GitHub for the assignment](#7-publish-the-project-on-github-for-the-assignment)
8. [How it works](#8-how-it-works)
9. [For the assignment video](#9-for-the-assignment-video)

---

## 1. Install Docker (once)

### What is Docker, in plain words?

This app needs a **database** (PostgreSQL with PostGIS, which understands maps) and a small **server program**. Installing and setting those up by hand is difficult. Docker puts each of them in a sealed box called a **container**, so you install **one** thing (Docker Desktop) and then start everything with **one command**. Your Windows or Mac is not changed in any other way.

### What you need

| | |
|---|---|
| Computer | Windows 10 or 11 (64-bit), or a Mac. Windows Home is fine. |
| Memory | 8 GB is comfortable. 4 GB is the minimum and will be slow. |
| Disk space | About 5 GB free. |
| Internet | Needed **once** to download Docker and the database image (roughly 1 to 2 GB in total, so use a good connection or Wi-Fi rather than mobile data). After that the app runs without internet. Only the map background, the fonts and the OpenStreetMap venue search need a connection. |

### Install on Windows

1. Go to **https://www.docker.com/products/docker-desktop/** and download **Docker Desktop for Windows**.
2. Double-click the downloaded file (`Docker Desktop Installer.exe`) and follow it. Leave **"Use WSL 2 instead of Hyper-V"** ticked if you are offered it.
3. When it finishes, **restart the computer** if asked.
4. Start **Docker Desktop** from the Start menu. Accept the licence. If it asks you to sign in you can choose to continue without signing in.
5. Wait one or two minutes until the whale icon in the taskbar stops moving and Docker Desktop says it is running (a green dot or "Engine running" at the bottom left).

If Docker says **"Virtualization is disabled"**, your computer's firmware setting must be switched on. It is usually called *Intel VT-x*, *AMD-V* or *SVM Mode* and is in the BIOS (restart and press the key shown at startup, often F2, F10 or Del). If you are not comfortable doing this, ask your IT colleague. It is a normal setting.

If Docker mentions **WSL**, open the Start menu, type `PowerShell`, right-click it, choose **Run as administrator**, type `wsl --update`, press Enter, then restart Docker Desktop.

### Install on a Mac

Download **Docker Desktop for Mac** from the same page (choose *Apple chip* for M1/M2/M3/M4 Macs, or *Intel chip* for older ones), drag it into Applications, open it and wait until it says it is running.

### Check that it works

Open **PowerShell** (Windows: Start menu, type `PowerShell`) or **Terminal** (Mac) and type:

```
docker --version
docker compose version
```

Each should print a version number. If you see "not recognized" or "command not found", Docker Desktop is not installed or not running yet, so start it and try again.

---

## 2. Get the project ready

1. **Unzip** the project: right-click the zip file and choose **Extract All** (Windows) or double-click it (Mac). Put the folder somewhere simple such as `C:\Users\YourName\wee-training-planner`. Do **not** run it from inside the zip.
2. If you ever ran an **older version** of this project, open its folder in PowerShell and run `docker compose down -v` once, so the old data does not get in the way.

---

## 3. Start the app

1. Open the project folder in File Explorer. Click the **address bar** at the top, type `powershell` and press **Enter**. A blue window opens, already inside the folder. (On a Mac, open Terminal, type `cd ` with a space, drag the folder into the window and press Return.)
2. Make sure **Docker Desktop is running**, then type:

```
docker compose up --build
```

3. The **first time** takes about 5 to 15 minutes while it downloads and builds. Lots of text scrolls past; that is normal. It is ready when you see a line like:

```
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

4. Open your web browser (Chrome or Edge) and go to **http://localhost:8000**

You should see the welcome screen. **Leave the PowerShell window open** while you use the app. (Prefer to close it? Use `docker compose up --build -d` instead, which runs quietly in the background.)

---

## 4. Use the app

### Try it with the sample file first

On the welcome screen press **Try the synthetic sample (4 EPAs)**. The app imports invented farmers for Chipoka, Chigulukwe, Nankumba and Rivirivi so you can explore everything safely.

### Import your real Solstice export

1. Press **Import Solstice export** (top right), then drop your `.xlsx` file in the box or press it to choose the file.
2. Press **Import**. The report tells you how many rows were read, where each location came from, and per EPA how many farmers are on the map, flagged or without a location.
3. Press **Open the map**.

You can import the same file again later (for example after Solstice is updated). Farmers are matched by serial number, so nothing is duplicated. Tick *Replace farmers already stored for the EPAs in this file* if some farmers have been removed from Solstice.

**What the app reads from the file:** EPA and district (from the *Country and Operational Area* column), ward, village, name, sex, phone number, category and the GPS location. It ignores dates of birth, disability, household composition and everything else.

**Which location is used:** the *GPS Coordinates* column first. If it is empty, the *Household Size* location, then the *phase 1* location.

### Step 1: Data

- Click a **district tab** at the top (Salima, Mangochi, Balaka).
- **Yellow notices** tell you about farmers with **no GPS location** (they cannot be mapped or invited) and about **flagged locations**: points that are far from the rest of their EPA (30 km by default) and are probably GPS errors. Flagged points are left out of plans. Tick *Show the flagged locations* to look at them.
- Click an **EPA** to zoom to it. The dashed EPA outline is drawn around the mapped farmers, so it is an estimate. To use official boundaries, press **Upload official EPA boundaries** (see below).
- **Possible venues:**
  - **Find places on OpenStreetMap** finds named primary and secondary schools, cooperatives, halls, churches and mosques, markets, health centres and government or extension offices within 10 km of your farmers.
  - **Import a list or boundaries** loads your own venue list (a CSV with `name`, `lat`, `lon`, and optionally `type` and `fee`).
  - **Add a venue on the map**: press it, click the spot, then name it. Use this for cooperatives and halls that OpenStreetMap does not know about.
  - The **type chips** switch venue types on or off, both on the map and in the plan.

> **OpenStreetMap is volunteer-made.** Many rural schools are on it, but cooperatives and village halls often are not. Check the list against what you know on the ground.

### Step 2: Plan

- **Farmers to mobilise:** type a number or drag the slider, or tick *Everyone in the selected EPAs*.
- **Invite from:** choose all EPAs or only some.
- **Best means:** *Lowest total cost*, or *Shortest trip for the farthest farmer* (fairest for everyone).
- **Cost assumptions:** the starting numbers are **examples**. Replace them with your project's real rates:
  - transport per road kilometre (paid for the round trip),
  - refreshments per farmer,
  - hire fee for venues whose fee is not recorded,
  - the **walk-in distance**: farmers closer than this walk and are not paid transport,
  - the road factor (road distance is straight-line distance multiplied by this; 1.3 is a common allowance for winding roads).
- Press **Find the best meeting place**. To test your own idea, press **Try a point on the map** and click anywhere.

### Step 3: Results

- The dark box gives the recommendation and, if the best spot is not an existing building, the **best actual venue** and how much more it costs.
- Click any option in the list: the map draws a line to every invited farmer, coloured by trip length, with a dotted **walk-in zone** around the venue.
- The detail shows total cost, cost per farmer, transport, refreshments, venue fee, average and farthest trip, how many walk in, which EPAs the farmers come from, and how many are women.
- **Download the attendee list** gives a CSV with Solstice serial number, name, sex, phone, EPA, ward, village and distance, ready for mobilisation. It contains personal data, so store and share it carefully.
- **Save this scenario** keeps the result in the database so you can compare options later.

### Official EPA boundaries (optional)

If you have an EPA shapefile from the Ministry of Agriculture or another source:

1. Open it in **QGIS**. Right-click the layer, choose **Export > Save Features As**, format **GeoJSON**, CRS **EPSG:4326 - WGS 84**, and save.
2. In the app choose a district tab, press **Upload official EPA boundaries**, pick the file and press **Import**. Only EPAs found in that district are kept. The district outline can be uploaded the same way if OpenStreetMap does not have it.

### Open the same data in QGIS

Layer > Add Layer > Add PostGIS Layers > New: host `localhost`, port `5433`, database `weeplanner`, user `gis`, password `gis`. The password is for your own computer only. Change it before putting this on a shared server.

---

## 5. Stop it, start it again, reset it

Run these in PowerShell inside the project folder:

| What you want | Command |
|---|---|
| Stop the app (your data is kept) | `docker compose down` (or press **Ctrl + C** in the window running it) |
| Start it again later | `docker compose up -d`, then open http://localhost:8000. Docker Desktop must be running first. |
| See what is happening | `docker compose logs api` |
| **Erase all data and start fresh** | `docker compose down -v` |

Your imported data lives inside Docker on your computer, not in the project folder. It survives restarts.

---

## 6. Something went wrong?

| What you see | What to do |
|---|---|
| `docker` is "not recognized" or "command not found" | Docker Desktop is not installed, or not started. Start it and wait for "running". Reopen PowerShell. |
| "Cannot connect to the Docker daemon" or "error during connect" | Docker Desktop is not running yet. Start it and wait a minute. |
| "port is already allocated" (8000 or 5433) | Another program uses that port. Close it, or in `docker-compose.yml` change `"8000:8000"` to `"8080:8000"` and open http://localhost:8080 instead. |
| The page says it cannot reach the planner's server | You opened the wrong address. Use **http://localhost:8000**. Check Docker Desktop shows both containers running. |
| Grey map with no background | The map pictures need internet. Your data and plans still work. Try the **Satellite** or **OpenStreetMap** choice in the layers button (top right). |
| "Could not reach OpenStreetMap" | The free OpenStreetMap server is busy or you are offline. Wait a minute and try again. You can also add venues by hand or import a list. |
| Import says the file is missing columns | Use the **beneficiary export from Solstice** (.xlsx) with the *Country and Operational Area* and *Serial Number* columns. |
| Many farmers are "flagged" | Their GPS point is far from the rest of their EPA. Check them in Solstice. You can raise the distance in the import window (for a very large EPA). |
| After updating the project, errors mention a missing column or table | Run `docker compose down -v` once, then `docker compose up --build`. The database design is only created the first time. |
| Anything else | Run `docker compose logs api` and read the last lines; they usually say what is wrong. |

---

## 7. Publish the project on GitHub for the assignment

The assignment asks for a **public** Git repository. Because the repository is public, **anyone can read everything in it**, so it must not contain real farmer data.

This project's `.gitignore` already blocks `.xlsx` and `.csv` files, except the synthetic sample. **Do not remove those rules, and keep your real Solstice file outside the project folder** (for example in your Documents).

The easiest way for a beginner:

1. Create a free account at **https://github.com**.
2. Install **GitHub Desktop** from **https://desktop.github.com** and sign in.
3. In GitHub Desktop choose **File > Add local repository**, pick the project folder (if it offers to create a repository, accept).
4. Look at the list of changed files. **Check that no real data file appears**, only code, the README and the synthetic sample.
5. Write a short summary (for example *First version*), press **Commit to main**, then **Publish repository**. **Untick "Keep this code private"** and publish.
6. Copy the repository address (`https://github.com/yourname/wee-training-planner`) for your submission.

Also ask AICC whether you may use the project for coursework. For the video, **use the synthetic sample**, not real farmers.

---

## 8. How it works

**Three parts:** a browser interface (Leaflet map), a small Python server (FastAPI) and a PostgreSQL + **PostGIS** database that does the spatial work.

| Question | PostGIS / method |
|---|---|
| Which locations are probably wrong? | The median point of each EPA with `percentile_cont`, then `ST_Distance` on `geography` to flag points far from it |
| What area does an EPA cover? | `ST_ConcaveHull` of its farmers, buffered with `ST_Buffer` |
| What is the district's shape? | Boundary ways from OpenStreetMap assembled with `ST_BuildArea` |
| Which venues are near the farmers? | `ST_DWithin` on a spatial index |
| Which EPA does a venue belong to? | Nearest farmer using the `<->` nearest-neighbour operator |
| Which N farmers are nearest a venue? | `ORDER BY ... <->` with `LIMIT N` (KNN on a GiST index), and `ST_Distance` |
| Where is the best free point? | A search over the real cost rule (below), seeded from every venue and sample farmer homes; the fairest point uses an exact smallest enclosing circle |

**Cost for one training**

```
road_km  = straight-line km x road factor
transport = 0                          if road_km <= walk-in distance
          = 2 x road_km x rate per km  otherwise              (round trip)
total    = sum of transport + refreshment x farmers + venue fee
```

**Project layout**

| Path | Contents |
|---|---|
| `db/schema.sql` | Tables for farmers, venues, boundaries and saved scenarios, with spatial indexes |
| `api/main.py` | The server and the PostGIS queries |
| `api/solstice.py` | The Solstice export reader |
| `api/osm.py` | OpenStreetMap search for boundaries and venues |
| `api/geo.py` | Helpers that propose the best free point |
| `web/` | The interface, including a bundled copy of Leaflet in `web/vendor` |
| `data/`, `web/samples/` | The synthetic sample export |
| `scripts/make_sample_data.py` | Regenerates the synthetic sample |
| `tests/` | `python -m unittest discover -s tests -v` and `node tests/test_csvparse.js` |

**Limitations to be honest about**

- Road distance is **estimated** from straight-line distance, not routed along real roads. Routing with `pgRouting` would be the next step.
- The best free point comes from a search, not a mathematical proof of the best answer. It is checked against every venue.
- EPA areas are estimates unless you upload official boundaries.
- A plan covers one training at a time. Splitting a large group into several sessions is future work.
- OpenStreetMap coverage of rural Malawi varies, so venue lists need checking.
- There is no login. Do not put this on a public server without adding one.

**Offline demo (advanced):** set `OSM_FIXTURE=path/to/file.json` for the `api` service to use recorded OpenStreetMap answers instead of the internet. The file holds `{"boundary": ..., "venues": ...}` in Overpass JSON format.

---

## 9. For the assignment video

A suggested 10-minute outline:

1. **The problem (2 min).** Mobilising farmers for trainings is costly when venues are far from where farmers live, and Solstice has the locations but no way to analyse them.
2. **The design (2 min).** Show the three parts and the table above. Explain why PostGIS and why Docker.
3. **Live demo with the synthetic sample (4 min).** Import, show the data checks, a district map with EPAs, find venues, plan for 40 farmers, compare the cheapest and fairest options, download the attendee list, open the data in QGIS.
4. **Limits and next steps (2 min).** Estimated roads, venue data quality, routing with pgRouting, multiple sessions.
