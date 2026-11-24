"""Paths, .env loading and the athlete profile.

Everything personal lives in the workspace folder (default ./me, override with RUNLAB_HOME).
It is gitignored: profile, goals, PBs, training log, Garmin data and generated reports never
leave the athlete's machine unless they choose to share them.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=None):
    """Read KEY=VALUE lines from .env into os.environ (existing variables win)."""
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


load_env()


def home():
    return os.path.abspath(os.environ.get("RUNLAB_HOME") or os.path.join(ROOT, "me"))


def path(*parts):
    return os.path.join(home(), *parts)


def data(*parts):
    return path("data", *parts)


def out(*parts):
    p = path("out", *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


DEFAULT_PROFILE = {
    "name": "",
    "sex": None,                 # "M" / "F": used only for age grading if ever added
    "birth_year": None,
    "units": "km",               # "km" or "mi" for paces in reports
    "hr": {
        "max": None,             # measured max HR (lab or race); else estimated from strap data
        "rest": None,
        "lt1": None,             # aerobic threshold HR (first lactate rise / VT1); easy cap
        "lt2": None,             # lactate turn point / threshold HR (LTP / VT2)
        "source": None,          # "lab 2024-12-06", "field test", "estimated"
        "strap_products": []     # extra Garmin product ids that count as a chest strap
    },
    "lab": None,                 # optional {"date", "stages": [[kmh, hr, lactate], ...]}
    "racing": {
        "super_shoes": False,    # races in carbon-plated super shoes
        "plate_gain": 0.025      # speed gain assumed for plates when converting training fitness to race estimates
    },
    "coach": {
        "has_coach": False,      # if true: follow the coach's plan as written, review and flag only
        "name": ""
    },
    "injury": {
        "watch": "",             # e.g. "achilles tendon"
        "pain_threshold": 2      # morning-after pain score (0-10) above which the next session backs off
    },
    "preferences": {
        "system": "",            # e.g. "threshold (Norwegian-style)", "Daniels", "Lydiard"
        "max_quality_per_week": 2,
        "notes": ""
    },
    "public_results": {
        "country": "",
        "profiles": []           # URLs of the athlete's public results pages (Power of 10, parkrun, Athlinks ...)
    }
}


def _merge(base, over):
    outd = dict(base)
    for k, v in (over or {}).items():
        outd[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return outd


def profile():
    p = path("profile.json")
    if not os.path.exists(p):
        return json.loads(json.dumps(DEFAULT_PROFILE))
    return _merge(DEFAULT_PROFILE, json.load(open(p, encoding="utf-8")))


def save_profile(prof):
    os.makedirs(home(), exist_ok=True)
    json.dump(prof, open(path("profile.json"), "w", encoding="utf-8"), indent=2)


def thresholds(prof=None, observed_max=None):
    """(lt1_hr, lt2_hr, hrmax, how) with defaults derived from max HR when not measured.
    Defaults: LT1 ~79 % and LT2 ~90 % of max HR (typical for trained runners). Measured values win."""
    prof = prof or profile()
    h = prof["hr"]
    hrmax = h.get("max") or observed_max
    lt1, lt2 = h.get("lt1"), h.get("lt2")
    how = h.get("source") or ("measured" if lt1 and lt2 else None)
    if hrmax and not lt2:
        lt2, how = round(hrmax * 0.90), "estimated from max HR"
    if hrmax and not lt1:
        lt1, how = round(hrmax * 0.79), "estimated from max HR"
    return lt1, lt2, hrmax, how or "unknown"
