"""Garmin Connect Personal API client and incremental sync (standard library only).

Credentials: GARMIN_PERSONAL_API_KEY in the environment or in .env (gitignored). Never commit it,
never paste it into chat. See docs/garmin-setup.md.

The key is exchanged for a 24 h bearer token; the token is used on the Connect web paths.
Per-call windows on the personal tier: daily summaries and HRV 180 days, sleep 28 days.
The personal tier is read-only: no workout or calendar writes, no gear.

Without a key, use `python3 -m runlab import PATH` on a Garmin data export (FIT files or the
account export zip): everything except sleep/HRV/readiness works from FIT files alone.
"""
import datetime as dt
import glob
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from . import config

BASE = os.environ.get("GARMIN_PERSONAL_API_BASE_URL", "https://personal.connectapi.garmin.com").rstrip("/")
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
RUN_TYPES = ("running", "track_running", "treadmill_running", "trail_running", "road_running",
             "indoor_running", "virtual_run", "ultra_run")
_token = None


class GarminError(SystemExit):
    pass


def key():
    k = (os.environ.get("GARMIN_PERSONAL_API_KEY") or "").strip()
    if not k:
        raise GarminError("GARMIN_PERSONAL_API_KEY is not set. Follow docs/garmin-setup.md, then put it in .env "
                          "(local) or in the cloud environment's variables (Claude Code on the web).")
    return k


def token(force=False):
    global _token
    if _token and not force:
        return _token
    req = urllib.request.Request(BASE + TOKEN_PATH, method="POST",
                                 headers={"Accept": "*/*", "Authorization": f"ApiKey {key()}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _token = r.read().decode().strip()
    except urllib.error.HTTPError as e:
        raise GarminError(f"token exchange failed: HTTP {e.code}. The key is wrong, revoked or expired: "
                          "create a new one (docs/garmin-setup.md).")
    except urllib.error.URLError as e:
        raise GarminError(f"cannot reach {BASE}: {e.reason}. In Claude Code on the web, add "
                          "personal.connectapi.garmin.com to the environment's allowed domains.")
    return _token


def request(path, query=None, accept="application/json", retried=0):
    q = {k: v for k, v in (query or {}).items() if v is not None}
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={"Accept": accept, "Authorization": f"Bearer {token()}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 401 and not retried:
            token(force=True)
            return request(path, query, accept, 1)
        if e.code == 429 and retried < 3:
            time.sleep(20 * (retried + 1))
            return request(path, query, accept, retried + 1)
        raise GarminError(f"HTTP {e.code} on {path}: {e.read()[:200].decode(errors='replace')}")


def get(path, query=None):
    body = request(path, query)
    return json.loads(body) if body else None


def check():
    p = get("/userprofile-service/userprofile/settings")
    return {"ok": True, "profile_fields": len(p) if isinstance(p, dict) else 0}


def activities(start=None, end=None, n=10000):
    acts, off = [], 0
    while len(acts) < n:
        page = get("/activitylist-service/activities/search/activities",
                   {"start": off, "limit": min(100, n - len(acts)), "startDate": start, "endDate": end})
        if not page:
            break
        acts += page
        off += len(page)
        time.sleep(0.3)
    return acts


def fit(aid, outdir):
    data = request(f"/download-service/files/activity/{aid}", accept="*/*")
    os.makedirs(outdir, exist_ok=True)
    saved = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.startswith("/") or ".." in n or not n.lower().endswith(".fit"):
                continue
            dest = os.path.join(outdir, f"{aid}_ACTIVITY.fit" if "_" not in n else os.path.basename(n))
            with open(dest, "wb") as f:
                f.write(z.read(n))
            saved.append(dest)
    return saved


def daily(start, end):
    d = get("/usersummary-service/v2/dailysummaries", {"startDate": start, "endDate": end})
    return d.get("data", d) if isinstance(d, dict) else (d or [])


def sleep(start, end):
    return get("/sleep-service/sleep/dailySleepSummariesByDate", {"startDate": start, "endDate": end}) or []


def hrv(start, end):
    d = get(f"/hrv-service/hrv/daily/{start}/{end}")
    return (d or {}).get("hrvSummaries", d if isinstance(d, list) else [])


# ---------------------------------------------------------------- local store
def _merge(name, rows, keyf):
    p = config.data(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    old = {}
    if os.path.exists(p):
        old = {str(r[keyf]): r for r in json.load(open(p)) if keyf in r}
    old.update({str(r[keyf]): r for r in rows if isinstance(r, dict) and keyf in r})
    json.dump(sorted(old.values(), key=lambda r: str(r[keyf])), open(p, "w"))
    return len(old)


def load(name):
    p = config.data(name)
    return json.load(open(p)) if os.path.exists(p) else []


def is_run(a):
    return (a.get("activityType") or {}).get("typeKey") in RUN_TYPES


def have_fit(aid):
    return bool(glob.glob(config.data("fit", f"{aid}_*.fit")) or glob.glob(config.data("fit", f"{aid}.fit")))


def _chunks(start, end, days):
    s = start
    while s <= end:
        e = min(end, s + dt.timedelta(days - 1))
        yield s.isoformat(), e.isoformat()
        s = e + dt.timedelta(1)


def sync(history_days=None, fit_days=120, all_fits=False, log=print):
    """Incremental pull. First run: full activity history (summaries are small), FIT files for runs in the
    last fit_days (or every run with all_fits), daily summaries and HRV 180 days, sleep 28 days (1 year on
    first run, in 28-day chunks). Later runs: from the last synced day."""
    today = dt.date.today()
    state_p = config.data("sync.json")
    state = json.load(open(state_p)) if os.path.exists(state_p) else {}
    first = not state
    since = dt.date.fromisoformat(state["last"]) - dt.timedelta(3) if state.get("last") else None
    start = since or (today - dt.timedelta(history_days) if history_days else None)
    log("activities" + (f" since {start}" if start else " (full history)") + " ...")
    acts = activities(start.isoformat() if start else None, today.isoformat())
    n = _merge("activities.json", acts, "activityId")
    log(f"  {len(acts)} pulled, {n} stored")

    wstart = since or today - dt.timedelta(179)
    for a, b in _chunks(wstart, today, 180):
        n = _merge("daily.json", daily(a, b), "calendarDate")
        try:
            hv = hrv(a, b)
            _merge("hrv.json", hv, "calendarDate")
        except GarminError:
            pass                                        # watches without HRV
    log(f"  daily summaries stored: {n}")
    sstart = since or today - dt.timedelta(364 if first else 27)
    for a, b in _chunks(sstart, today, 28):
        n = _merge("sleep.json", sleep(a, b), "calendarDate")
        time.sleep(0.3)
    log(f"  sleep nights stored: {n}")

    got, runs = 0, [a for a in load("activities.json") if is_run(a)]
    cutoff = today - dt.timedelta(fit_days)
    for a in sorted(runs, key=lambda a: a["startTimeLocal"], reverse=True):
        d = dt.date.fromisoformat(a["startTimeLocal"][:10])
        if (all_fits or d >= cutoff) and not have_fit(a["activityId"]):
            try:
                fit(a["activityId"], config.data("fit"))
                got += 1
            except GarminError as e:
                log(f"  FIT {a['activityId']} failed: {e}")
            time.sleep(0.5)
    log(f"  new FIT files: {got}")
    state["last"] = today.isoformat()
    json.dump(state, open(state_p, "w"))


def fetch_fits(ids):
    for aid in ids:
        if not have_fit(aid):
            fit(aid, config.data("fit"))


# ---------------------------------------------------------------- manual import (no API key)
def import_export(src, log=print):
    """Copy FIT files from a folder or zip (Garmin 'Export Original', or the account data export) into
    me/data/fit, and build a minimal activities.json from them so every report works without the API."""
    from .fit import decode, start_unix, SPORTS_RUN
    os.makedirs(config.data("fit"), exist_ok=True)
    files = []
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                if n.lower().endswith(".fit") and ".." not in n:
                    dest = config.data("fit", os.path.basename(n))
                    with open(dest, "wb") as f:
                        f.write(z.read(n))
                    files.append(dest)
                elif n.lower().endswith(".zip") and ".." not in n:     # nested zips in the account export
                    tmp = config.data("_nested.zip")
                    with open(tmp, "wb") as f:
                        f.write(z.read(n))
                    import_export(tmp, log=lambda *_: None)
                    os.remove(tmp)
    else:
        for f in glob.glob(os.path.join(src, "**", "*.fit"), recursive=True) + \
                 glob.glob(os.path.join(src, "**", "*.FIT"), recursive=True):
            dest = config.data("fit", os.path.basename(f))
            if os.path.abspath(f) != os.path.abspath(dest):
                with open(f, "rb") as a, open(dest, "wb") as b:
                    b.write(a.read())
            files.append(dest)
    acts = []
    for f in glob.glob(config.data("fit", "*.fit")) + glob.glob(config.data("fit", "*.FIT")):
        try:
            d = decode(f)
        except Exception:                               # noqa: BLE001 - skip unreadable files
            continue
        s = d["session"]
        if s.get("sport") not in SPORTS_RUN or not d["records"]:
            continue
        aid = os.path.basename(f).split("_")[0].split(".")[0]
        u = start_unix(d)
        local = dt.datetime.fromtimestamp(u).strftime("%Y-%m-%d %H:%M:%S")
        hrs = [r[3] for r in d["records"] if r[3]]
        acts.append({"activityId": aid, "activityName": "Run", "startTimeLocal": local,
                     "activityType": {"typeKey": "running"}, "eventType": {"typeKey": "uncategorized"},
                     "distance": s.get("dist_m"), "duration": s.get("timer_s"), "movingDuration": s.get("timer_s"),
                     "elapsedDuration": s.get("elapsed_s"), "averageHR": s.get("hr") or (sum(hrs) / len(hrs) if hrs else None),
                     "maxHR": s.get("max_hr"), "source": "fit-import"})
    n = _merge("activities.json", acts, "activityId")
    log(f"imported {len(files)} FIT files; {len(acts)} runs; activities stored: {n}")
