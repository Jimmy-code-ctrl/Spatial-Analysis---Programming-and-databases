"""Small geometry helpers used to propose 'ideal' meeting points.

Distances reported to the user always come from PostGIS (geography); these
flat-earth helpers only decide where to *look* for a good point.
"""
import math
import random

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQ = 111.320


class Plane:
    """Local flat-map coordinates in km around (lon0, lat0). Pass the km-per-degree values
    measured by PostGIS so this approximation agrees with the database's ellipsoid distances."""
    def __init__(self, lon0, lat0, km_per_deg_lon=None, km_per_deg_lat=None):
        self.lon0, self.lat0 = lon0, lat0
        self.kx = km_per_deg_lon or KM_PER_DEG_LON_EQ * math.cos(math.radians(lat0))
        self.ky = km_per_deg_lat or KM_PER_DEG_LAT

    def xy(self, lon, lat):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    def lonlat(self, x, y):
        return (self.lon0 + x / self.kx, self.lat0 + y / self.ky)


def nearest(pts, c, n):
    return sorted(pts, key=lambda p: (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2)[:n]


def geometric_median(pts, start, iters=80):
    """Weiszfeld: the point minimising total distance to pts."""
    x, y = start
    for _ in range(iters):
        nx = ny = den = 0.0
        for px, py in pts:
            d = max(math.hypot(px - x, py - y), 1e-9)
            nx += px / d
            ny += py / d
            den += 1 / d
        nx, ny = nx / den, ny / den
        done = math.hypot(nx - x, ny - y) < 1e-4
        x, y = nx, ny
        if done:
            break
    return x, y


def min_enclosing_center(pts):
    """Exact smallest circle containing pts (Welzl, iterative). Its centre is the point
    that minimises the farthest farmer's distance."""
    P = list(pts)
    random.Random(1).shuffle(P)

    def inside(c, p):
        return math.hypot(p[0] - c[0][0], p[1] - c[0][1]) <= c[1] + 1e-9

    def from2(a, b):
        return (((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), math.hypot(a[0] - b[0], a[1] - b[1]) / 2)

    def from3(a, b, c):
        d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(d) < 1e-12:  # collinear: the widest pair decides
            return max((from2(a, b), from2(a, c), from2(b, c)), key=lambda t: t[1])
        ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1])
              + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d
        uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0])
              + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d
        return ((ux, uy), math.hypot(ux - a[0], uy - a[1]))

    circ = (P[0], 0.0)
    for i, p in enumerate(P):
        if inside(circ, p):
            continue
        circ = (p, 0.0)
        for j in range(i):
            q = P[j]
            if inside(circ, q):
                continue
            circ = from2(p, q)
            for k in range(j):
                r = P[k]
                if not inside(circ, r):
                    circ = from3(p, q, r)
    return circ[0]


def ideal_point(pts, n, mode, seeds):
    """Best free point for the n nearest farmers. Alternates 'pick the n nearest' and
    'move to the best centre of those n' from several starting seeds. Each seed's own
    score is also considered, so the answer is never worse than any seed."""
    def score(c):
        d = [math.hypot(p[0] - c[0], p[1] - c[1]) for p in nearest(pts, c, n)]
        return sum(d) if mode == "cost" else max(d)

    best = None
    for s in seeds:
        options = [s]
        c = s
        for _ in range(10):
            cohort = nearest(pts, c, n)
            new = geometric_median(cohort, c) if mode == "cost" else min_enclosing_center(cohort)
            moved = math.hypot(new[0] - c[0], new[1] - c[1])
            c = new
            if moved < 0.05:
                break
        options.append(c)
        for o in options:
            sc = score(o)
            if best is None or sc < best[0]:
                best = (sc, o)
    return best[1]


def transport_cost(pts, c, n, circ, walk, rate):
    """Round-trip transport bill for the n farmers nearest to c (same rule as the SQL):
    nothing is paid within the walk-in distance."""
    d = sorted(math.hypot(p[0] - c[0], p[1] - c[1]) for p in pts)[:n]
    return sum(0.0 if x * circ <= walk else 2 * x * circ * rate for x in d)


def best_cost_point(pts, n, circ, walk, rate, seeds):
    """Point that minimises the real transport cost, including the walk-in cutoff.
    Scores every seed, then refines the best few with a compass (pattern) search."""
    def f(c):
        return transport_cost(pts, c, n, circ, walk, rate)

    scored = sorted(((f(s), s) for s in seeds), key=lambda t: t[0])[:3]
    best = scored[0]
    for fc, c in scored:
        step = 2.0
        for _ in range(150):
            if step < 0.02:
                break
            trials = [(f(t), t) for t in (
                (c[0] + dx * step, c[1] + dy * step)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (.7, -.7), (-.7, .7), (-.7, -.7)))]
            v, t = min(trials, key=lambda x: x[0])
            if v < fc - 1e-9:
                fc, c = v, t
            else:
                step /= 2
        if fc < best[0]:
            best = (fc, c)
    return best[1]
