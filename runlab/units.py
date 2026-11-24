"""Time and pace formatting/parsing."""
import re

MILE = 1609.344

DISTANCES = {            # canonical event name -> metres
    "400m": 400, "800m": 800, "1500m": 1500, "Mile": MILE, "3000m": 3000, "2 miles": 2 * MILE,
    "5K": 5000, "5000m": 5000, "parkrun": 5000, "5 miles": 5 * MILE, "10K": 10000, "10000m": 10000,
    "10 miles": 10 * MILE, "Half marathon": 21097.5, "20 miles": 20 * MILE, "Marathon": 42195,
}

ALIASES = {
    "1 mile": "Mile", "mile": "Mile", "1m": "Mile", "5k": "5K", "5km": "5K", "10k": "10K", "10km": "10K",
    "hm": "Half marathon", "half": "Half marathon", "half marathon": "Half marathon", "hmar": "Half marathon",
    "mar": "Marathon", "marathon": "Marathon", "5m": "5 miles", "5 mile": "5 miles", "10m": "10 miles",
    "10 mile": "10 miles", "parkrun": "parkrun", "pr": "parkrun", "3000": "3000m", "5000": "5000m",
    "10000": "10000m", "1500": "1500m", "800": "800m", "400": "400m", "3k": "3000m", "2m": "2 miles",
    "20m": "20 miles", "20 mile": "20 miles",
}


def event_name(s):
    k = s.strip()
    if k in DISTANCES:
        return k
    return ALIASES.get(k.lower().replace("road", "").strip(), ALIASES.get(k.lower(), None))


def hms(s, frac=False):
    if s is None:
        return "-"
    s = round(s, 1 if frac else 0)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    sec = f"{sec:04.1f}" if frac else f"{int(sec):02d}"
    return f"{int(h)}:{int(m):02d}:{sec}" if h else f"{int(m)}:{sec}"


def parse_time(t):
    """'41:30', '1:32:10', '17:05.42', '3:05:00' or seconds -> seconds."""
    if isinstance(t, (int, float)):
        return float(t)
    t = t.strip().rstrip("s")
    parts = [float(p) for p in re.split(r"[:]", t)]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def pace(kmh, unit="km"):
    """'m:ss' per km (or per mile) from km/h."""
    if not kmh:
        return "-"
    s = 3600 / kmh * (MILE / 1000 if unit == "mi" else 1)
    m, sec = divmod(round(s), 60)
    return f"{m}:{sec:02d}"


def pace_s(kmh):
    return 3600 / kmh if kmh else None


def kmh_from_pace(p):
    """'3:30' (per km) -> km/h."""
    return 3600 / parse_time(p)
