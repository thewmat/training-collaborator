"""Workout library built on Daniels' intensities, with HR caps from the athlete's thresholds.

Only used when the athlete asks for sessions. If the athlete has a coach, Claude reviews the coach's
sessions and sets pace bands for them; it does not replace them.

Daniels' per-session volume limits (share of weekly volume):
  L  long run  <= 25 % of the week (or 150 min)       M  <= 20 % (or 29 km)
  T  threshold <= 10 %                                I  <= 8 % (or 10 km), reps 3-5 min
  R  repetition <= 5 % (or 8 km), reps <= 2 min, full recovery

Threshold reps with short rests are run at LT2 EFFORT, not continuous-LT2 pace: 1 km reps off
1 min sit ~1.5 % faster than continuous T, 6-min reps ~1.5 % slower. Guard them with flat rep-end HR,
not pace alone: ease 3 s/km when rep-end HR climbs more than 3 bpm rep on rep or passes the cap.
Lead with pace; HR only becomes a check after ~2 min of each rep (HR lags).
"""
from . import vdot
from .units import pace


def band(kmh, lo, hi, unit="km"):
    """'fast-slow' pace band: speeds from kmh*(1+lo) (slow end) to kmh*(1+hi) (fast end)."""
    return f"{pace(kmh * (1 + hi), unit)}-{pace(kmh * (1 + lo), unit)}"


def library(vd, weekly_km, lt1=None, lt2=None, unit="km"):
    p = vdot.paces(vd)
    T, I, R, M = p["T"], p["I"], p["R"], p["M"]
    cap = lambda x: f"rep-end HR <= {x}" if x else "no HR cap (no thresholds set)"
    t_km, i_km, r_km = weekly_km * 0.10, min(weekly_km * 0.08, 10), min(weekly_km * 0.05, 8)
    L = []
    L.append({"key": "easy", "type": "E", "name": "Easy run", "pace": f"{pace(p['E'][1], unit)}-{pace(p['E'][0], unit)}",
              "hr": f"under {lt1}" if lt1 else "conversational", "rule": "HR governs, not pace. There is no too slow."})
    L.append({"key": "long", "type": "L", "name": f"Long run, up to {min(weekly_km * 0.25, 150 / 60 * p['E'][1] * 0.9):.0f} km",
              "pace": f"{pace(p['E'][1], unit)}-{pace(p['E'][0], unit)}", "hr": f"under {lt1}" if lt1 else "easy",
              "rule": "Easy band. Cap 25 % of the week or 150 min. Fuel 60 g/h from 30 min on runs over 90 min."})
    reps_1k = max(4, min(10, round(t_km)))
    L.append({"key": "cruise_1k", "type": "T", "name": f"{reps_1k} x 1 km, 1 min jog (threshold reps)",
              "pace": band(T, 0.010, 0.020, unit), "hr": cap(lt2 and lt2 + 2),
              "rule": "LT2 effort; short rest allows ~1.5 % faster than continuous T. Rep-end HR flat from rep 2."})
    mi = max(3, min(6, round(t_km / 1.6)))
    L.append({"key": "cruise_mile", "type": "T", "name": f"{mi} x 1 mile (or 2 km), 1 min jog",
              "pace": band(T, -0.005, 0.005, unit), "hr": cap(lt2),
              "rule": "Continuous-T pace. Last rep no more than 3 s/km faster than the others."})
    L.append({"key": "sub_t", "type": "T-", "name": "5 x 6 min, 1 min jog (sub-threshold)",
              "pace": band(T, -0.025, -0.010, unit), "hr": cap(lt2 and lt2 - 3),
              "rule": "Controlled. Should feel like you could do two more reps."})
    L.append({"key": "tempo", "type": "T", "name": f"Tempo {min(40, max(15, round(t_km / (T / 60))))} min continuous",
              "pace": band(T, -0.01, 0.0, unit), "hr": f"<= {lt2} throughout" if lt2 else "comfortably hard",
              "rule": "Start on the slow edge. At the cap, ease immediately; no last-minute kick."})
    L.append({"key": "interval", "type": "I", "name": f"{max(4, min(6, round(i_km)))} x 1 km, equal-time jog (VO2max)",
              "pace": band(I, -0.005, 0.005, unit), "hr": "ignore (lags)",
              "rule": "3-5 min reps. Never faster than I pace: faster adds cost, not stimulus."})
    L.append({"key": "reps", "type": "R", "name": f"{max(6, min(12, round(r_km / 0.4)))} x 400 m, 400 m jog",
              "pace": band(R, -0.005, 0.005, unit), "hr": "ignore",
              "rule": "Relaxed and fast. Full recovery: the jog must leave you ready for the next rep at the same pace."})
    L.append({"key": "marathon", "type": "M", "name": f"{min(29, round(weekly_km * 0.20))} km at marathon pace in a long run",
              "pace": band(M, -0.01, 0.01, unit), "hr": f"{lt2 - 10}-{lt2 - 5}" if lt2 else "steady",
              "rule": "Rehearse race fuel and shoes. Cap 20 % of the week or 29 km."})
    L.append({"key": "hills_x", "type": "X", "name": "15-20 x 200 m uphill (~5 %), jog down",
              "pace": "5K effort", "hr": "ignore",
              "rule": "Even time and power per rep; the X-element of a threshold week. Add 5 reps a week."})
    L.append({"key": "strides", "type": "S", "name": "6 x 20 s strides after an easy run", "pace": f"~{pace(R, unit)}",
              "hr": "ignore", "rule": "Fast, relaxed, full walk-back recovery. Not sprints."})
    return L


TEMPLATES = {
    "threshold": ["Mon easy", "Tue AM sub_t / PM cruise_1k", "Wed easy", "Thu cruise_mile", "Fri easy or rest",
                  "Sat hills_x", "Sun long"],
    "daniels": ["Mon easy", "Tue cruise_mile", "Wed easy + strides", "Thu easy", "Fri interval", "Sat easy", "Sun long"],
    "marathon": ["Mon easy", "Tue cruise_1k", "Wed easy + strides", "Thu easy", "Fri tempo", "Sat easy", "Sun long with marathon"],
}


def text(vd, weekly_km, lt1=None, lt2=None, system="daniels", unit="km"):
    L = library(vd, weekly_km, lt1, lt2, unit)
    out = [f"Sessions at VDOT {vd:.1f}, {weekly_km:.0f} km/week" + (f", LT1 {lt1} / LT2 {lt2} bpm" if lt2 else ""), ""]
    for s in L:
        out.append(f"[{s['type']}] {s['name']}\n      pace {s['pace']}/{unit}   HR {s['hr']}\n      {s['rule']}")
    if system in TEMPLATES:
        out += ["", f"Week shape ({system}): " + " | ".join(TEMPLATES[system])]
    return "\n".join(out)
