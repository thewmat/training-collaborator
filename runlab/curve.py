"""Fitness curve: running speed at a fixed heart rate, tracked over time.

The single number that tracks aerobic fitness week to week is the pace you run at your threshold
heart rate (LT2) and at your aerobic threshold heart rate (LT1). It needs no race and no test:
every steady run and every long rep is a data point.

Points
  Each FIT file gives candidate points: device laps of structured runs (warm-up lap dropped when there
  are 3+ laps) or, for a single-lap run, the whole run from minute 5. The first 60 s of a lap are
  dropped (HR still rising). Kept: >= 800 m, >= 4 min (shorter reps never reach steady-state HR, so
  their HR understates the effort), 6-25 km/h, stops < 30 % of the lap, HR 100 to max.
HR validity
  Wrist HR under-reads in intervals and locks onto cadence. When the window holds enough points from a
  chest strap (external HR sensor in the FIT), only strap points are used: at least 8 points over a
  15 bpm spread, or the line cannot be trusted to reach threshold HR. Otherwise wrist points are
  used without cadence-locked laps, and the result is marked low confidence.
Fit
  Weighted reduced-major-axis line kmh = a + b * HR (weight = lap minutes capped at 15), three passes
  of a 2.5 x MAD residual trim. RMA, not least squares: both axes are noisy.
Read
  pace at LT1 HR and LT2 HR, for a 30-day window ending each week. Threshold pace -> VDOT
  (Daniels T = 88 % VDOT) -> race estimates.
Comparing single sessions
  HR rises through a session, so compare sessions matched on cumulative work time
  (analyse.compare_matched), never rep 4 of one day against rep 1 of another.
"""
import datetime as dt
import glob
import json
import os
import statistics as st

from . import config, vdot
from .analyse import load
from .units import pace

WINDOW_DAYS = 30
MIN_DIST, MIN_MOV, SKIP_S = 800, 240, 60
MIN_KMH, MAX_KMH, MAX_STOP = 6.0, 25.0, 1.3
OUTLIER_K = 2.5
CACHE = "curve_points.json"


def _stats(recs, t0, t1):
    seg = [r for r in recs if t0 <= r[6] < t1]
    dist = mov = hrw = hrt = lock = lockn = 0.0
    for p, q in zip(seg, seg[1:]):
        d_t = min(q[6] - p[6], 10)
        if q[2] is not None and q[2] >= 4:
            dist += q[1] - p[1]; mov += d_t
        if q[3]:
            hrw += q[3] * d_t; hrt += d_t
            if q[4]:
                lockn += d_t; lock += d_t * (abs(q[3] - q[4]) <= 3)
    return {"dist": dist, "mov": mov, "elapsed": (seg[-1][6] - seg[0][6]) if seg else 0,
            "hr": hrw / hrt if hrt else None, "lock": lock / lockn if lockn else 0.0}


def run_points(path, day, name, strap_products=()):
    d, recs = load(path, strap_products)
    laps = [l for l in d["laps"] if l["timer_s"] >= 5 and l.get("t0") is not None]
    windows = []
    if len(laps) <= 1:
        windows.append((0, 300, 1e12, "whole run from min 5"))
    else:
        for i, l in enumerate(laps):
            if i == 0 and len(laps) >= 3:
                continue
            windows.append((i + 1, l["t0"] + SKIP_S, l["t0"] + l["elapsed_s"], "lap"))
    pts = []
    for lap, a, b, kind in windows:
        w = _stats(recs, a, b)
        if not w["mov"] or not w["hr"]:
            continue
        pts.append({"file": os.path.basename(path), "date": day, "name": name, "lap": lap, "kind": kind,
                    "km": round(w["dist"] / 1000, 3), "min": round(w["mov"] / 60, 2),
                    "elapsed_min": round(w["elapsed"] / 60, 2), "kmh": round(w["dist"] / w["mov"] * 3.6, 3),
                    "hr": round(w["hr"], 1), "lock": round(w["lock"], 2), "hr_source": d["hr_source"]})
    return pts


def screen(p, hrmax):
    if p["km"] * 1000 < MIN_DIST or p["min"] * 60 < MIN_MOV - SKIP_S:
        return "short"
    if p["elapsed_min"] > MAX_STOP * p["min"]:
        return "stopped"
    if not MIN_KMH <= p["kmh"] <= MAX_KMH:
        return "speed out of range"
    if not 100 <= p["hr"] <= (hrmax or 210):
        return "HR out of range"
    if p["hr_source"] != "strap" and p["lock"] >= 0.5:
        return "cadence lock"
    return None


def points(refresh=False, prof=None):
    """Candidate points for every run with a FIT file (cached by file name)."""
    from .garmin import load as load_store, is_run
    prof = prof or config.profile()
    sp = tuple(prof["hr"].get("strap_products") or ())
    cache_p = config.data(CACHE)
    cache = {} if refresh or not os.path.exists(cache_p) else json.load(open(cache_p))
    acts = {str(a["activityId"]): a for a in load_store("activities.json") if is_run(a)}
    for f in glob.glob(config.data("fit", "*.fit")):
        base = os.path.basename(f)
        if base in cache:
            continue
        aid = base.split("_")[0].split(".")[0]
        a = acts.get(aid)
        if not a:
            cache[base] = []
            continue
        try:
            cache[base] = run_points(f, a["startTimeLocal"][:10], a.get("activityName") or "Run", sp)
        except Exception:                               # noqa: BLE001 - corrupt file: skip, keep going
            cache[base] = []
    json.dump(cache, open(cache_p, "w"))
    return [p for ps in cache.values() for p in ps]


def wfit(pts):
    w = [min(p["min"], 15) for p in pts]
    x = [p["hr"] for p in pts]; y = [p["kmh"] for p in pts]
    sw = sum(w); mx = sum(a * b for a, b in zip(w, x)) / sw; my = sum(a * b for a, b in zip(w, y)) / sw
    sxx = sum(a * (b - mx) ** 2 for a, b in zip(w, x)); syy = sum(a * (b - my) ** 2 for a, b in zip(w, y))
    sxy = sum(a * (b - mx) * (c - my) for a, b, c in zip(w, x, y))
    if sxx <= 0 or syy <= 0:
        return my, 0.0, 0.0
    b = (syy / sxx) ** 0.5 * (1 if sxy >= 0 else -1)
    return my - b * mx, b, sxy * sxy / (sxx * syy)


def robust(pts):
    kept, dropped = list(pts), []
    for _ in range(3):
        a, b, _ = wfit(kept)
        res = [p["kmh"] - (a + b * p["hr"]) for p in kept]
        mad = st.median([abs(r) for r in res]) * 1.4826 or 1e-9
        keep = [p for p, r in zip(kept, res) if abs(r) <= OUTLIER_K * mad]
        dropped += [p for p, r in zip(kept, res) if abs(r) > OUTLIER_K * mad]
        if len(keep) == len(kept) or len(keep) < 6:
            break
        kept = keep
    a, b, r2 = wfit(kept)
    return kept, dropped, a, b, r2


def fit_window(pts, end, days=WINDOW_DAYS, hrmax=None):
    start = end - dt.timedelta(days - 1)
    win = [p for p in pts if start.isoformat() <= p["date"] <= end.isoformat() and not screen(p, hrmax)]
    strap = [p for p in win if p["hr_source"] == "strap"]
    strap_ok = len(strap) >= 8 and max(p["hr"] for p in strap) - min(p["hr"] for p in strap) >= 15
    use, conf = (strap, "strap") if strap_ok else (win, "wrist (low confidence)" if len(strap) < len(win) else "strap")
    if len(use) < 6 or max(p["hr"] for p in use) - min(p["hr"] for p in use) < 8:
        return None
    kept, dropped, a, b, r2 = robust(use)
    if b <= 0:
        return None
    return {"start": start.isoformat(), "end": end.isoformat(), "a": a, "b": b, "r2": r2, "n": len(kept),
            "dropped": len(dropped), "hr_confidence": conf, "points": kept,
            "hr_lo": min(p["hr"] for p in kept), "hr_hi": max(p["hr"] for p in kept)}


def build(asof=None, weeks=26, refresh=False, prof=None):
    prof = prof or config.profile()
    pts = points(refresh, prof)
    if not pts:
        raise SystemExit("no usable runs with FIT files: run python3 -m runlab sync (or import)")
    strap_max = max((p["hr"] for p in pts if p["hr_source"] == "strap"), default=None)
    lt1, lt2, hrmax, how = config.thresholds(prof, strap_max)
    if not (lt1 and lt2):
        raise SystemExit("set hr.max (or hr.lt1 and hr.lt2) in me/profile.json first")
    today = dt.date.fromisoformat(asof) if asof else dt.date.today()
    last = max(dt.date.fromisoformat(p["date"]) for p in pts if p["date"] <= today.isoformat())
    ends = sorted({last} | {last - dt.timedelta(7 * k) for k in range(1, weeks)})
    trend = []
    for e in ends:
        f = fit_window(pts, e, hrmax=hrmax)
        if not f:
            continue
        k1, k2 = f["a"] + f["b"] * lt1, f["a"] + f["b"] * lt2
        trend.append({"end": e.isoformat(), "kmh_lt1": round(k1, 3), "kmh_lt2": round(k2, 3),
                      "pace_lt1": pace(k1), "pace_lt2": pace(k2), "n": f["n"], "r2": round(f["r2"], 2),
                      "hr_confidence": f["hr_confidence"],
                      "extrapolated": not (f["hr_lo"] - 3 <= lt2 <= f["hr_hi"] + 3)})
    # all-time best 30-day window (sampled monthly over the whole record)
    first = min(dt.date.fromisoformat(p["date"]) for p in pts)
    best = None
    e = first + dt.timedelta(WINDOW_DAYS)
    while e <= last:
        f = fit_window(pts, e, hrmax=hrmax)
        if f and f["hr_confidence"] == "strap" and f["hr_lo"] - 3 <= lt2 <= f["hr_hi"] + 3:
            k2 = f["a"] + f["b"] * lt2
            if not best or k2 > best["kmh_lt2"]:
                best = {"end": e.isoformat(), "kmh_lt2": round(k2, 3), "pace_lt2": pace(k2)}
        e += dt.timedelta(14)
    cur = fit_window(pts, last, hrmax=hrmax)
    out = {"asof": today.isoformat(), "thresholds": {"lt1": lt1, "lt2": lt2, "max": hrmax, "source": how},
           "trend": trend, "best": best, "current": None, "headline": "Not enough steady running with HR yet."}
    if cur and trend:
        k1, k2 = cur["a"] + cur["b"] * lt1, cur["a"] + cur["b"] * lt2
        vd = vdot.vdot_from_threshold_kmh(k2)
        gain = prof["racing"]["plate_gain"] if prof["racing"].get("super_shoes") else 0.0
        solid = [t for t in trend if not t["extrapolated"]] or trend
        four = next((t for t in reversed(solid) if t["end"] <= (last - dt.timedelta(27)).isoformat()), solid[0])
        d4 = 3600 / k2 - 3600 / four["kmh_lt2"]
        weeks_span = max(1, (last - dt.date.fromisoformat(four["end"])).days / 7)
        out["current"] = {
            "window": f"{cur['start']} to {cur['end']}", "n": cur["n"], "r2": round(cur["r2"], 2),
            "hr_confidence": cur["hr_confidence"], "a": cur["a"], "b": cur["b"],
            "pace_lt1": pace(k1), "pace_lt2": pace(k2), "kmh_lt1": round(k1, 3), "kmh_lt2": round(k2, 3),
            "easy_band": f"{pace(cur['a'] + cur['b'] * (lt1 - 3))}-{pace(cur['a'] + cur['b'] * (lt1 - 11))}",
            "vdot": round(vd, 1), "race_gain": gain,
            "estimates": {k: round(v) for k, v in vdot.equivalents(vd, race_gain=gain).items()},
            "change_4wk_s_km": round(d4, 1), "rate_s_km_per_week": round(d4 / weeks_span, 1),
            "points": [{k: p[k] for k in ("date", "name", "lap", "km", "min", "kmh", "hr", "hr_source")} for p in cur["points"]],
        }
        word = "faster" if d4 < -1 else "slower" if d4 > 1 else "about the same as"
        out["headline"] = (f"Threshold pace (HR {lt2}) is {pace(k2)}/km: {abs(d4):.0f} s/km {word} than 4 weeks ago"
                           if word != "about the same as" else
                           f"Threshold pace (HR {lt2}) is {pace(k2)}/km, about the same as 4 weeks ago") + \
            f". Easy pace (HR under {lt1}) {out['current']['easy_band']}/km. VDOT {vd:.1f}."
        if best:
            gap = 3600 / k2 - 3600 / best["kmh_lt2"]
            out["current"]["vs_best_s_km"] = round(gap, 1)
    json.dump(out, open(config.out("curve.json"), "w"), indent=1)
    return out


def text(c):
    lines = [c["headline"], ""]
    t = c["thresholds"]
    lines.append(f"Thresholds: LT1 {t['lt1']} / LT2 {t['lt2']} bpm ({t['source']})")
    if c["current"]:
        k = c["current"]
        lines.append(f"Window {k['window']}: {k['n']} points, r2 {k['r2']}, HR {k['hr_confidence']}")
        if c["best"]:
            lines.append(f"Best on record: {c['best']['pace_lt2']}/km at LT2 (30 days to {c['best']['end']}); "
                         f"now {k['vs_best_s_km']:+.0f} s/km")
    lines.append("")
    lines.append("week ending   LT2 pace  LT1 pace  points")
    for r in c["trend"]:
        lines.append(f"{r['end']}    {r['pace_lt2']:>6}    {r['pace_lt1']:>6}    {r['n']:>3}"
                     + ("  (LT2 outside data: extrapolated)" if r["extrapolated"] else "")
                     + ("  wrist HR" if r["hr_confidence"] != "strap" else ""))
    return "\n".join(lines)
