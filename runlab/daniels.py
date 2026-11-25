"""Detailed Daniels tables, computed from the Daniels/Gilbert equations at any VDOT.

Nothing here is a copied table: every pace comes from the oxygen-cost and time-to-exhaustion
curves in vdot.py, so the tables work at any VDOT and to the second.

  zone grid        recovery, easy, moderate/high aerobic, then race intensities from the marathon to
                   the mile: % of VO2max, Daniels' % of max HR, % of HR reserve, HR, pace per km and mile
  tempo durations  threshold pace for continuous tempo runs of 20-60 minutes (longer = slower)
  interval splits  100 m to 2000 m at R, I and T pace and at mile, 5K, 10K, half and marathon race pace
  race table       equivalent times and paces from 1500 m to 50K, with Daniels' % of VO2max for each
  intensity points Daniels' points per minute by % of VO2max (or % of max HR), per run and per week
  heat             Daniels' projected slowing of a 5K in heat (race-day planning context only)

Heart-rate columns are Daniels' generic % of max HR. Measured LT1/LT2 caps (profile hr.lt1/lt2) win over
them for every prescription.
"""
import bisect
import math

from . import vdot as V
from .units import DISTANCES, MILE, hms, pace

KM_PER_MILE = MILE / 1000

# ---------------------------------------------------------------- %VO2max <-> %HRmax
def hrmax_frac(pct_vo2):
    """Daniels' % of max HR for a fraction of VO2max (59 % VO2max = 65 % HRmax, 100 % = 100 %)."""
    return min(1.0, 0.65 + 0.35 * (pct_vo2 - 0.59) / 0.41)


def vo2_frac(pct_hr):
    """Inverse of hrmax_frac."""
    return 0.59 + 0.41 * (pct_hr - 0.65) / 0.35


def kmh_at(vd, pct_vo2):
    return V.kmh_at_fraction(vd, pct_vo2)


# ---------------------------------------------------------------- zone grid
RACES = [("Marathon", "Marathon"), ("Half", "Half marathon"), ("15K", "15K"), ("12K", "12K"), ("10K", "10K"),
         ("8K", "8K"), ("5K", "5K"), ("3K", "3000m"), ("Mile", "Mile")]


def zone_grid(vd, hrmax=None, rest=None):
    """Rows of {zone, pct_vo2, pct_hr, hr, pct_hrr, kmh, time_s (races only)}."""
    rows = []

    def add(zone, pct_hr=None, pct_vo2=None, time_s=None, kmh=None):
        pv = pct_vo2 if pct_vo2 is not None else vo2_frac(pct_hr)
        ph = pct_hr if pct_hr is not None else hrmax_frac(pv)
        hr = hrmax * ph if hrmax else None
        rows.append({"zone": zone, "pct_vo2": pv, "pct_hr": ph, "hr": hr,
                     "pct_hrr": (hr - rest) / (hrmax - rest) if hr and rest else None,
                     "kmh": kmh or kmh_at(vd, pv), "time_s": time_s})

    add("Recovery", pct_hr=0.65)
    add("Easy (low)", pct_hr=0.70)
    add("Easy (high)", pct_hr=0.75)
    # moderate / high aerobic: one third and two thirds of the way from the top of easy to marathon,
    # in pace (seconds per km) and in HR
    m_t = V.race_time(vd, DISTANCES["Marathon"])
    m_kmh, m_hr = DISTANCES["Marathon"] / m_t * 3.6, hrmax_frac(V.pct_max(m_t / 60))
    e_kmh = kmh_at(vd, vo2_frac(0.75))
    for label, f in (("Moderate aerobic", 1 / 3), ("High aerobic", 2 / 3)):
        kmh = 3600 / (3600 / e_kmh + (3600 / m_kmh - 3600 / e_kmh) * f)
        add(label, pct_hr=0.75 + (m_hr - 0.75) * f, pct_vo2=pct_vo2_of_speed(vd, kmh), kmh=kmh)
    for label, ev in RACES:
        t = V.race_time(vd, DISTANCES[ev])
        add(label, pct_vo2=V.pct_max(t / 60), time_s=t, kmh=DISTANCES[ev] / t * 3.6)
    return rows


# ---------------------------------------------------------------- tempo durations
TEMPO = [(20, 1.0), (25, 1.012), (30, 1.022), (35, 1.027), (40, 1.033), (45, 1.038), (50, 1.043),
         (55, 1.0487), (60, 1.055)]


def tempo_table(vd):
    """[(minutes, kmh, km covered)]: T pace for 20 min, slowed for longer continuous tempo runs."""
    t = V.paces(vd)["T"]
    return [(m, t / f, t / f * m / 60) for m, f in TEMPO]


# ---------------------------------------------------------------- interval splits
SPLITS = [100, 200, 300, 400, 600, 800, 1000, 1200, 1600, 2000]


def split_paces(vd):
    p = V.paces(vd)
    out = [("R", p["R"]), ("I", p["I"]), ("T", p["T"])]
    for label, ev in (("Mile race", "Mile"), ("5K race", "5K"), ("10K race", "10K"), ("Half race", "Half marathon"),
                      ("Marathon", "Marathon")):
        out.append((label, DISTANCES[ev] / V.race_time(vd, DISTANCES[ev]) * 3.6))
    return out


def split_table(vd):
    """{pace label: {distance m: seconds}}."""
    return {label: {d: d / (kmh / 3.6) for d in SPLITS} for label, kmh in split_paces(vd)}


# ---------------------------------------------------------------- race table
RACE_TABLE = ["1500m", "Mile", "2000m", "3000m", "2 miles", "5K", "8K", "5 miles", "10K", "12K", "15K",
              "10 miles", "20K", "Half marathon", "25K", "30K", "Marathon", "50K"]


def race_table(vd, race_gain=0.0):
    """[(event, seconds, kmh, pct_vo2)]. race_gain speeds results up (super shoes on a training-fitness VDOT)."""
    rows = []
    for e in RACE_TABLE:
        t = V.race_time(vd, DISTANCES[e])
        rows.append((e, t / (1 + race_gain), DISTANCES[e] / t * 3.6 * (1 + race_gain), V.pct_max(t / 60)))
    return rows


# ---------------------------------------------------------------- intensity points
# Daniels' intensity points per minute: (% VO2max, % HRmax, points/min). Above VO2max HR is maxed out.
POINTS = [(0.50, 0.56, 0.100), (0.59, 0.65, 0.100), (0.60, 0.66, 0.110), (0.61, 0.67, 0.122), (0.62, 0.68, 0.135),
          (0.63, 0.69, 0.150), (0.64, 0.70, 0.167), (0.65, 0.71, 0.183), (0.66, 0.72, 0.200), (0.67, 0.73, 0.217),
          (0.68, 0.74, 0.233), (0.69, 0.75, 0.250), (0.71, 0.76, 0.283), (0.72, 0.77, 0.300), (0.73, 0.78, 0.317),
          (0.74, 0.79, 0.333), (0.75, 0.80, 0.350), (0.76, 0.81, 0.367), (0.77, 0.82, 0.392), (0.78, 0.83, 0.417),
          (0.79, 0.84, 0.442), (0.80, 0.85, 0.467), (0.81, 0.86, 0.492), (0.82, 0.87, 0.517), (0.83, 0.88, 0.550),
          (0.84, 0.89, 0.583), (0.86, 0.90, 0.617), (0.87, 0.91, 0.650), (0.88, 0.92, 0.683), (0.90, 0.93, 0.723),
          (0.91, 0.94, 0.763), (0.92, 0.95, 0.800), (0.93, 0.96, 0.840), (0.94, 0.97, 0.883), (0.96, 0.98, 0.917),
          (0.98, 0.99, 0.960), (1.00, 1.00, 1.000), (1.05, None, 1.250), (1.10, None, 1.500), (1.15, None, 1.750),
          (1.20, None, 2.100)]
WEEKLY_LEVELS = [(50, "novice high-school"), (100, "advanced high-school"), (150, "collegiate"), (200, "elite")]


def _interp(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x)
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def points_per_min(pct_vo2=None, pct_hr=None):
    """Points per minute from % of VO2max (pace basis) or % of max HR (HR basis). Below the table = 0.1."""
    if pct_hr is not None:
        rows = [r for r in POINTS if r[1] is not None]
        return _interp([r[1] for r in rows], [r[2] for r in rows], pct_hr)
    return _interp([r[0] for r in POINTS], [r[2] for r in POINTS], pct_vo2)


def pct_vo2_of_speed(vd, kmh):
    return V.vo2(kmh * 1000 / 60) / vd


def run_points(samples, vd=None, hrmax=None, use_hr=False):
    """samples: [(seconds, kmh, hr)] in 60 s bins. HR basis when use_hr and hrmax (chest strap), else pace."""
    total = 0.0
    for sec, kmh, hr in samples:
        if use_hr and hrmax and hr:
            total += sec / 60 * points_per_min(pct_hr=hr / hrmax)
        elif vd and kmh:
            total += sec / 60 * points_per_min(pct_vo2=pct_vo2_of_speed(vd, kmh))
    return total


def level(weekly):
    name = "below novice"
    for pts, label in WEEKLY_LEVELS:
        if weekly >= pts:
            name = label
    return name


# ---------------------------------------------------------------- heat
HEAT_F = [60, 65, 70, 75, 80, 85, 90, 95, 100]


def heat_factor(temp_c):
    """Daniels: no cost up to 60 F (15.6 C); then about 0.75 % of 5K time per 5 F (2.8 C)."""
    f = temp_c * 9 / 5 + 32
    return 1 + 0.0075 * max(0.0, (f - 60) / 5)


def heat_table(time_s):
    """[(deg C, seconds)] at Daniels' 5 F steps from 60 F."""
    return [((f - 32) * 5 / 9, time_s * heat_factor((f - 32) * 5 / 9)) for f in HEAT_F]


# ---------------------------------------------------------------- text
def text(vd, hrmax=None, rest=None, unit="km", sections=None, race_gain=0.0):
    want = set(sections or ["zones", "tempo", "splits", "races", "points", "heat"])
    L = [f"Daniels tables at VDOT {vd:.1f}"]
    if "zones" in want:
        L += ["", "Zone grid" + ("" if hrmax else " (set hr.max in the profile for HR columns)"),
              "  zone               %VO2  %HRmax   HR  %HRR   /km    /mi    race"]
        for r in zone_grid(vd, hrmax, rest):
            L.append(f"  {r['zone']:<18} {r['pct_vo2'] * 100:4.0f}  {r['pct_hr'] * 100:5.0f}  "
                     f"{round(r['hr']) if r['hr'] else '-':>4}  {round(r['pct_hrr'] * 100) if r['pct_hrr'] else '-':>4}  "
                     f"{pace(r['kmh']):>5}  {pace(r['kmh'], 'mi'):>5}  {hms(r['time_s']) if r['time_s'] else '':>8}")
        L.append("  HR here is Daniels' generic % of max HR. Measured LT1/LT2 caps win.")
    if "tempo" in want:
        L += ["", "Continuous tempo: T pace by duration", "  " + "  ".join(f"{m:>5}'" for m, _, _ in tempo_table(vd)),
              "  " + "  ".join(f"{pace(k, unit):>6}" for _, k, _ in tempo_table(vd)),
              "  " + "  ".join(f"{km:>4.1f}km" for _, _, km in tempo_table(vd))]
    if "splits" in want:
        L += ["", "Interval splits", "  pace        /" + unit + "  " + "".join(f"{d:>7}" for d in SPLITS)]
        for label, kmh in split_paces(vd):
            L.append(f"  {label:<10} {pace(kmh, unit):>5}  " + "".join(f"{hms(d / (kmh / 3.6), frac=d < 400):>7}" for d in SPLITS))
    if "races" in want:
        L += ["", "Race equivalents" + (f" (+{race_gain * 100:.1f} % race-shoe gain)" if race_gain else ""),
              "  event            time     /km    /mi   %VO2max"]
        for e, t, kmh, pv in race_table(vd, race_gain):
            L.append(f"  {e:<14} {hms(t):>8}  {pace(kmh):>5}  {pace(kmh, 'mi'):>5}   {pv * 100:5.1f}")
    if "points" in want:
        L += ["", "Intensity points per minute (Daniels)"]
        for label, kmh in [("Easy", kmh_at(vd, 0.66)), ("M", V.paces(vd)["M"]), ("T", V.paces(vd)["T"]),
                           ("I", V.paces(vd)["I"]), ("R", V.paces(vd)["R"])]:
            pv = pct_vo2_of_speed(vd, kmh)
            L.append(f"  {label:<5} {pace(kmh, unit):>5}/{unit}  {pv * 100:5.1f} % VO2max  {points_per_min(pv):.3f} pts/min")
        L.append("  Weekly levels: " + ", ".join(f"{p} {n}" for p, n in WEEKLY_LEVELS))
    if "heat" in want:
        t5 = V.race_time(vd, 5000)
        L += ["", f"Heat: projected 5K ({hms(t5)} at 16 C or cooler). Race-day planning only; fitness reads stay raw.",
              "  " + "  ".join(f"{c:>5.0f}C" for c, _ in heat_table(t5)), "  " + "  ".join(f"{hms(t):>6}" for _, t in heat_table(t5))]
    return "\n".join(L)


# ---------------------------------------------------------------- points from the athlete's runs
def bins(recs, width=60):
    """[(seconds, kmh, mean hr)] per `width` seconds of timer time from analyse.load records."""
    out, i0 = [], 0
    for i in range(1, len(recs)):
        if recs[i][0] - recs[i0][0] >= width or i == len(recs) - 1:
            dt_ = recs[i][0] - recs[i0][0]
            if dt_ > 0:
                hrs = [r[3] for r in recs[i0:i + 1] if r[3]]
                out.append((dt_, (recs[i][1] - recs[i0][1]) / dt_ * 3.6, sum(hrs) / len(hrs) if hrs else None))
            i0 = i
    return out


def weekly_points(vd, weeks=8, prof=None, asof=None):
    """Daniels points per Monday-start week from FIT files (summary pace when a run has no FIT).
    HR basis on chest-strap runs when max HR is known, pace basis otherwise."""
    import datetime as dt
    from . import analyse, config, garmin
    prof = prof or config.profile()
    _, _, hrmax, _ = config.thresholds(prof)
    today = dt.date.fromisoformat(asof) if asof else dt.date.today()
    first = today - dt.timedelta(today.weekday()) - dt.timedelta(7 * (weeks - 1))
    weeks_out = {(first + dt.timedelta(7 * k)).isoformat(): {"week": (first + dt.timedelta(7 * k)).isoformat(),
                                                             "points": 0.0, "runs": 0, "hr_basis": 0}
                 for k in range(weeks)}
    for a in garmin.load("activities.json"):
        if not garmin.is_run(a):
            continue
        d = dt.date.fromisoformat(a["startTimeLocal"][:10])
        if not first <= d <= today:
            continue
        wk = weeks_out[(d - dt.timedelta(d.weekday())).isoformat()]
        pts, hr_used = None, False
        if garmin.have_fit(a["activityId"]):
            try:
                dd, recs = analyse.load(analyse.find_fit(a["activityId"]), tuple(prof["hr"].get("strap_products") or ()))
                hr_used = dd["hr_source"] == "strap" and bool(hrmax)
                pts = run_points(bins(recs), vd, hrmax, use_hr=hr_used)
            except (SystemExit, Exception):              # noqa: BLE001 - unreadable FIT: fall back to the summary
                pts = None
        if pts is None and a.get("distance") and (a.get("movingDuration") or a.get("duration")):
            t = a.get("movingDuration") or a["duration"]
            pts = run_points([(t, a["distance"] / t * 3.6, None)], vd)
        wk["points"] += pts or 0
        wk["runs"] += 1
        wk["hr_basis"] += hr_used
    rows = list(weeks_out.values())
    for r in rows:
        r["points"] = round(r["points"], 1)
        r["level"] = level(r["points"])
    return rows
