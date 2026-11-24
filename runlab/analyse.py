"""Review one run from its Garmin FIT file: splits, reps, pacing discipline, HR drift and zones.

Method
  clock     timer time: timer stop/start pauses are removed, so auto-pause does not count.
  splits    time at each split boundary, interpolated between 1 s records.
  reps      work laps found by splitting device laps into fast and slow groups (largest speed gap,
            at least 12 %). Warm-up and cool-down are the slow laps before the first and after the last rep.
  rep_end   mean HR over the last 30 s of a rep: the HR that matters on reps (HR lags ~2 min,
            so whole-rep averages understate the effort).
  checks    pace creep (last rep > 3 s/km faster than the others), rising rep-end HR (> 3 bpm rep on rep),
            reps ending over the LT2 cap, inverted pacing inside reps, easy runs over the LT1 cap.
  halves    first and second half by distance; negative split when the second half is faster.
  evenness  coefficient of variation of full-split pace.
  drift     aerobic decoupling: speed per heartbeat, first half vs second half from minute 5
            (+ = HR rose at the same speed). Under 5 % on a steady run is good.
  zones     time below LT1, LT1-LT2, above LT2 from the athlete's thresholds.
  hr        'strap' (external sensor recorded), 'wrist' (indicative only) or 'none'; 'cadence lock'
            when wrist HR sits within 3 bpm of cadence for over half the run.
  bests     fastest rolling 400 m, 1 km, mile, 5 km, 10 km, half and marathon inside the run.
"""
import glob
import os
import statistics as st

from . import config
from .fit import decode
from .units import MILE, hms, pace

MAX_MS = 8.0          # 28.8 km/h: faster steps between records are GPS spikes
BESTS = [(400, "400 m"), (1000, "1 km"), (MILE, "Mile"), (3000, "3 km"), (5000, "5 km"), (10000, "10 km"),
         (MILE * 10, "10 miles"), (21097.5, "Half marathon"), (42195, "Marathon")]


def find_fit(arg):
    if os.path.exists(str(arg)):
        return str(arg)
    hits = glob.glob(config.data("fit", f"{arg}_*.fit")) + glob.glob(config.data("fit", f"{arg}.fit"))
    if not hits:
        raise SystemExit(f"no FIT file for {arg} in {config.data('fit')} (run: python3 -m runlab sync, or fit {arg})")
    return hits[0]


def latest_fit():
    files = sorted(glob.glob(config.data("fit", "*.fit")), key=os.path.getmtime)
    if not files:
        raise SystemExit("no FIT files yet: run python3 -m runlab sync")
    # newest activity by start time, not file time
    return max(files, key=lambda f: decode(f)["t0"] or 0)


def load(path, strap_products=()):
    d = decode(path, strap_products)
    recs, excess = [], 0.0
    for t, dist, kmh, hr, cad, alt, pw in d["records"]:
        dist -= excess
        if recs and dist < recs[-1][1]:
            dist = recs[-1][1]
        if recs and t > recs[-1][6]:                    # GPS spike: cap the step at MAX_MS, shift the rest down
            cap = recs[-1][1] + MAX_MS * (t - recs[-1][6])
            if dist > cap:
                excess += dist - cap
                dist = cap
        clock = t - sum(min(b, t) - a for a, b in d["pauses"] if a < t)
        recs.append([clock, dist, kmh, hr, cad, alt, t, pw])
    return d, recs


def at(recs, dist, i0=0):
    """Interpolated (clock, index) where cumulative distance reaches dist."""
    for i in range(max(i0, 1), len(recs)):
        if recs[i][1] >= dist:
            (ta, da), (tb, db) = recs[i - 1][:2], recs[i][:2]
            return (ta + (tb - ta) * (dist - da) / (db - da) if db > da else tb), i
    return recs[-1][0], len(recs) - 1


def seg_stats(recs, i0, i1):
    seg = recs[i0:i1 + 1]
    hrs = [r[3] for r in seg if r[3]]
    cads = [r[4] for r in seg if r[4]]
    alts = [r[5] for r in seg if r[5] is not None]
    pws = [r[7] for r in seg if r[7]]
    return {"hr": round(st.mean(hrs)) if hrs else None, "max_hr": max(hrs) if hrs else None,
            "cad": round(st.mean(cads)) if cads else None, "power": round(st.mean(pws)) if pws else None,
            "up_m": round(sum(max(0, b - a) for a, b in zip(alts, alts[1:])), 1),
            "down_m": round(sum(max(0, a - b) for a, b in zip(alts, alts[1:])), 1)}


def splits(recs, step):
    total, rows, t_prev, i_prev, k = recs[-1][1], [], 0.0, 0, 1
    while True:
        edge = min(k * step, total)
        t, i = at(recs, edge, i_prev)
        dist = edge - (k - 1) * step
        if dist < 50:
            break
        secs = t - t_prev
        rows.append({"n": k, "dist_m": round(dist, 1), "time_s": round(secs, 1),
                     "pace_s_km": round(secs / dist * 1000, 1), **seg_stats(recs, i_prev, i), "full": dist >= step - 1})
        if edge >= total:
            break
        t_prev, i_prev, k = t, i, k + 1
    return rows


def rolling_best(recs, dist):
    best, j = None, 0
    for i in range(len(recs)):
        while j < len(recs) and recs[j][1] - recs[i][1] < dist:
            j += 1
        if j == len(recs):
            break
        (ta, da), (tb, db) = recs[j - 1][:2], recs[j][:2]
        need = recs[i][1] + dist
        tend = ta + (tb - ta) * (need - da) / (db - da) if db > da else tb
        s = tend - recs[i][0]
        if s > 0 and (best is None or s < best[0]):
            best = (s, recs[i][1])
    return best


def hr_quality(d, recs):
    if d["hr_source"] == "none":
        return "none"
    both = [(r[3], r[4]) for r in recs if r[3] and r[4]]
    if both and sum(abs(h - c) <= 3 for h, c in both) / len(both) > 0.5:
        return "cadence lock"
    return d["hr_source"]


def window(recs, t0, t1):
    """Stats over wall-clock window [t0, t1] (record field 6)."""
    seg = [r for r in recs if t0 <= r[6] <= t1]
    if len(seg) < 2:
        return None
    dist = seg[-1][1] - seg[0][1]
    clock = seg[-1][0] - seg[0][0]
    hrs = [r[3] for r in seg if r[3]]
    end = [r[3] for r in seg if r[3] and r[6] >= t1 - 30]
    first = [(r[1], r[0]) for r in seg]
    half = dist / 2
    th = next((c for d_, c in first if d_ - seg[0][1] >= half), seg[-1][0]) - seg[0][0]
    return {"dist_m": round(dist, 1), "time_s": round(clock, 1),
            "kmh": round(dist / clock * 3.6, 2) if clock else None,
            "hr": round(st.mean(hrs)) if hrs else None, "max_hr": max(hrs) if hrs else None,
            "end_hr": round(st.mean(end)) if end else None,
            "first_half_s": round(th, 1), "second_half_s": round(clock - th, 1),
            "power": round(st.mean([r[7] for r in seg if r[7]])) if any(r[7] for r in seg) else None}


def find_reps(laps):
    """Indices of work laps: the fast side of the largest gap in lap speed (>= 12 %)."""
    cand = [(i, l) for i, l in enumerate(laps) if l.get("kmh") and l["timer_s"] >= 8]
    if len(cand) < 3:
        return []
    speeds = sorted(l["kmh"] for _, l in cand)
    gaps = [(b / a, a, b) for a, b in zip(speeds, speeds[1:]) if a > 0]
    ratio, lo, hi = max(gaps)
    if ratio < 1.12:
        return []
    cut = (lo + hi) / 2
    return [i for i, l in cand if l["kmh"] >= cut]


def analyse(path, official=None, step=1000.0, lap=None, prof=None):
    prof = prof or config.profile()
    d, recs = load(path, tuple(prof["hr"].get("strap_products") or ()))
    if lap:                                             # one device lap only (a race inside a longer session)
        L = d["laps"][lap - 1]
        recs = [r for r in recs if L["t0"] <= r[6] <= L["t0"] + L["elapsed_s"]]
        c0, d0 = recs[0][0], recs[0][1]
        for r in recs:
            r[0] -= c0; r[1] -= d0
        d["laps"] = [L]
    if len(recs) < 30:
        raise SystemExit(f"{path}: too few records to analyse")
    observed_max = max((r[3] for r in recs if r[3]), default=None)
    lt1, lt2, hrmax, how = config.thresholds(prof, observed_max if d["hr_source"] == "strap" else None)
    gps = recs[-1][1]
    scale = official / gps if official else 1.0
    if official:
        for r in recs:
            r[1] *= scale
    total_t, total_d = recs[-1][0], recs[-1][1]
    sp = splits(recs, step)
    full = [s for s in sp if s["full"]]
    paces = [s["pace_s_km"] for s in full]
    half_t, _ = at(recs, total_d / 2)

    def ef(a, b):
        seg = [r for r in recs if a <= r[0] < b and r[3]]
        if len(seg) < 30:
            return None
        return (seg[-1][1] - seg[0][1]) / (seg[-1][0] - seg[0][0]) / st.mean(r[3] for r in seg)

    mid = (300 + total_t) / 2
    e1, e2 = ef(300, mid), ef(mid, total_t + 1)
    zones = {"below_lt1": 0, "lt1_lt2": 0, "above_lt2": 0}
    if lt1 and lt2:
        for a, b in zip(recs, recs[1:]):
            if a[3]:
                k = "below_lt1" if a[3] < lt1 else "lt1_lt2" if a[3] <= lt2 else "above_lt2"
                zones[k] += min(b[0] - a[0], 10)
    hr_all = [r[3] for r in recs if r[3]]
    cad_all = [r[4] for r in recs if r[4]]
    bests = []
    for dist, label in BESTS:
        if total_d >= dist * 1.01:
            b = rolling_best(recs, dist)
            if b:
                bests.append({"label": label, "dist_m": dist, "time_s": round(b[0], 1), "from_km": round(b[1] / 1000, 2)})

    # reps
    laps = d["laps"]
    idx = find_reps(laps)
    reps = []
    for n, i in enumerate(idx, 1):
        L = laps[i]
        w = window(recs, L.get("t0", 0), L.get("t0", 0) + L["elapsed_s"])
        if not w:
            continue
        nxt = laps[i + 1] if i + 1 < len(laps) and (i + 1) not in idx and 10 <= laps[i + 1]["timer_s"] <= 600 \
            and laps[i + 1].get("t0") is not None else None
        reps.append({"n": n, "lap": i + 1, **w, "pace": pace(w["kmh"]),
                     "rest_s": nxt["timer_s"] if nxt else None,
                     "rest_end_hr": window(recs, nxt["t0"], nxt["t0"] + nxt["elapsed_s"])["end_hr"]
                     if nxt and nxt.get("t0") is not None and window(recs, nxt["t0"], nxt["t0"] + nxt["elapsed_s"]) else None})
    hrq = hr_quality(d, recs)
    checks = rep_checks(reps, lt2, hrq) if reps else easy_checks(recs, lt1, hrq, total_t)

    return {
        "file": os.path.basename(path), "start_unix": (d["t0"] or 0) + 631065600,
        "gps_dist_m": round(gps, 1), "dist_m": round(total_d, 1), "scale": round(scale, 4),
        "time_s": round(total_t, 1), "pace_s_km": round(total_t / total_d * 1000, 1),
        "hr": round(st.mean(hr_all)) if hr_all else None, "max_hr": max(hr_all) if hr_all else None,
        "cad": round(st.mean(cad_all)) if cad_all else None, "hr_quality": hrq,
        "thresholds": {"lt1": lt1, "lt2": lt2, "max": hrmax, "source": how},
        "elev_up_m": round(sum(max(0, b[5] - a[5]) for a, b in zip(recs, recs[1:]) if a[5] is not None and b[5] is not None), 1),
        "split_m": step, "splits": sp,
        "halves": {"first_s": round(half_t, 1), "second_s": round(total_t - half_t, 1),
                   "diff_s": round(total_t - 2 * half_t, 1), "negative": total_t - half_t < half_t},
        "evenness_cv_pct": round(st.pstdev(paces) / st.mean(paces) * 100, 2) if len(paces) > 1 else None,
        "fade_s_km": round(paces[-1] - st.mean(paces[:-1]), 1) if len(paces) > 2 else None,
        "drift_pct": round((e1 - e2) / e1 * 100, 1) if e1 and e2 else None,
        "zones_s": {k: round(v) for k, v in zones.items()},
        "bests": bests, "reps": reps, "checks": checks,
        "laps": [{k: l.get(k) for k in ("dist_m", "timer_s", "kmh", "hr", "max_hr", "cad", "power")} for l in laps],
    }


def rep_checks(reps, lt2, hrq):
    out = []
    ps = [3600 / r["kmh"] for r in reps if r["kmh"]]
    if len(ps) >= 3:
        rest = st.mean(ps[:-1])
        if rest - ps[-1] > 3:
            out.append(f"pace creep: last rep {rest - ps[-1]:.0f} s/km faster than the others")
        spread = max(ps) - min(ps)
        if spread > 6:
            out.append(f"uneven reps: {spread:.0f} s/km between fastest and slowest")
    inv = [r["n"] for r in reps if r["first_half_s"] and r["second_half_s"] and r["second_half_s"] > r["first_half_s"] * 1.04]
    if inv:
        out.append("faded inside rep " + ", ".join(map(str, inv)))
    if hrq in ("strap",):
        ends = [r["end_hr"] for r in reps if r["end_hr"]]
        # rep 1 ends low (HR still climbing out of the warm-up), so the flat-HR rule starts at rep 2
        jumps = [i + 2 for i, (a, b) in enumerate(zip(ends, ends[1:])) if i >= 1 and b - a > 3]
        if jumps:
            out.append("rep-end HR jumped > 3 bpm into rep " + ", ".join(map(str, jumps)))
        if lt2:
            over = [r["n"] for r in reps if r["end_hr"] and r["end_hr"] > lt2 + 2]
            if over:
                out.append(f"rep-end HR over LT2+2 ({lt2 + 2}) in rep " + ", ".join(map(str, over))
                           + " (fine for 10K-and-faster sessions; a threshold session should not do this)")
    elif hrq != "none":
        out.append(f"HR is {hrq}: HR checks skipped; judge the session on pace")
    return out


def easy_checks(recs, lt1, hrq, total_t):
    out = []
    if hrq == "strap" and lt1:
        over = sum(min(b[0] - a[0], 10) for a, b in zip(recs, recs[1:]) if a[3] and a[3] >= lt1)
        if over > 60:
            out.append(f"{hms(over)} at or above LT1 ({lt1} bpm): if this was an easy run it was not easy")
    elif hrq != "none":
        out.append(f"HR is {hrq}: indicative only")
    return out


def report(a, title="", unit="km"):
    lines = [title or a["file"]]
    lines.append(f"  {a['dist_m'] / 1000:.2f} km in {hms(a['time_s'])} ({hms(a['pace_s_km'])}/km)"
                 + (f"  GPS {a['gps_dist_m'] / 1000:.2f} km scaled x{a['scale']}" if a["scale"] != 1 else ""))
    lines.append(f"  HR {a['hr']} avg / {a['max_hr']} max [{a['hr_quality']}]  cadence {a['cad']}  climb {a['elev_up_m']} m")
    h = a["halves"]
    lines.append(f"  halves {hms(h['first_s'])} / {hms(h['second_s'])} ({'negative' if h['negative'] else 'positive'}, "
                 f"{h['diff_s']:+.0f} s)  evenness CV {a['evenness_cv_pct']}%  fade {a['fade_s_km']} s/km  drift {a['drift_pct']}%")
    t = a["thresholds"]
    if t["lt1"]:
        z = a["zones_s"]
        lines.append(f"  zones (LT1 {t['lt1']} / LT2 {t['lt2']}, {t['source']})  <LT1 {hms(z['below_lt1'])}  "
                     f"LT1-LT2 {hms(z['lt1_lt2'])}  >LT2 {hms(z['above_lt2'])}")
    if a["reps"]:
        lines.append("  reps   dist    time   pace   HR  end  max  rest  rest-end")
        for r in a["reps"]:
            lines.append(f"  {r['n']:>4} {r['dist_m']:>6.0f} {hms(r['time_s']):>7} {r['pace']:>6} {r['hr'] or '-':>4} "
                         f"{r['end_hr'] or '-':>4} {r['max_hr'] or '-':>4} {hms(r['rest_s']) if r['rest_s'] else '-':>5} "
                         f"{r['rest_end_hr'] or '-':>5}")
    else:
        lines.append(f"  {'km' if a['split_m'] == 1000 else 'mi':>3}   dist   time   pace   HR  max  cad   +m")
        for s in a["splits"]:
            lines.append(f"  {s['n']:>3} {s['dist_m']:>6.0f} {hms(s['time_s']):>6} {hms(s['pace_s_km']):>6} "
                         f"{s['hr'] or '-':>4} {s['max_hr'] or '-':>4} {s['cad'] or '-':>4} {s['up_m']:>4.0f}")
    if a["bests"]:
        lines.append("  bests  " + "  ".join(f"{b['label']} {hms(b['time_s'])}" for b in a["bests"]))
    for c in a["checks"]:
        lines.append(f"  ! {c}")
    return "\n".join(lines)


def compare_matched(path_a, path_b, prof=None, bin_min=8, skip_s=150):
    """Compare two interval sessions on CUMULATIVE WORK TIME: HR rises through a session, so rep 4 of one
    day must be compared with rep 4 (same minutes of work) of the other, never with its rep 1.
    The first skip_s seconds of every rep are dropped (HR still rising). Returns rows per work-time bin:
    {from_min, to_min, a: {kmh, hr}, b: {kmh, hr}}."""
    prof = prof or config.profile()

    def work_samples(path):
        d, recs = load(path, tuple(prof["hr"].get("strap_products") or ()))
        idx = find_reps(d["laps"])
        out, done = [], 0.0
        for i in idx:
            L = d["laps"][i]
            seg = [r for r in recs if L["t0"] <= r[6] <= L["t0"] + L["elapsed_s"]]
            for p, q in zip(seg, seg[1:]):
                dt_ = q[0] - p[0]
                if q[6] - L["t0"] >= skip_s and q[3] and dt_ > 0:
                    out.append((done + (q[6] - L["t0"]), q[1] - p[1], dt_, q[3]))
            done += L["timer_s"]
        return out, d["hr_source"]

    A, qa = work_samples(path_a)
    B, qb = work_samples(path_b)
    rows = []
    top = min(max((s[0] for s in A), default=0), max((s[0] for s in B), default=0))
    k = 0
    while k * bin_min * 60 < top:
        lo, hi = k * bin_min * 60, (k + 1) * bin_min * 60
        row = {"from_min": k * bin_min, "to_min": (k + 1) * bin_min}
        for key, S in (("a", A), ("b", B)):
            seg = [s for s in S if lo <= s[0] < hi]
            dist, tim = sum(s[1] for s in seg), sum(s[2] for s in seg)
            row[key] = {"kmh": round(dist / tim * 3.6, 2) if tim else None,
                        "hr": round(sum(s[3] * s[2] for s in seg) / tim, 1) if tim else None}
        rows.append(row)
        k += 1
    return {"hr_quality": [qa, qb], "rows": rows}
