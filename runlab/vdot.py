"""Jack Daniels / Jimmy Gilbert VDOT model: race equivalents and training paces.

  VO2 cost of running at v m/min:      VO2(v) = -4.6 + 0.182258 v + 0.000104 v^2
  fraction of VO2max held for t min:   %max(t) = 0.8 + 0.1894393 e^(-0.012778 t) + 0.2989558 e^(-0.1932605 t)
  VDOT = VO2(race speed) / %max(race duration)

Training intensities as fractions of VDOT (Daniels' Running Formula):
  E (easy / long)   59-74 %      T (threshold)   88 %       I (interval)  97.5 %
  M (marathon)      marathon race pace at this VDOT
  R (repetition)    mile race pace at this VDOT, 2.3 % slower (matches the published R column)
Checked against the published tables: VDOT 50 gives 5K 19:57, T 4:15/km, I 3:55/km.
"""
import math

from .units import DISTANCES, MILE, hms, pace

R_FACTOR = 1.023
FRACTIONS = {"E_slow": 0.59, "E_fast": 0.74, "T": 0.88, "I": 0.975}


def vo2(v):
    return -4.6 + 0.182258 * v + 0.000104 * v * v


def pct_max(t_min):
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot(dist_m, time_s):
    t = time_s / 60
    return vo2(dist_m / t) / pct_max(t)


def speed_for_vo2(v_o2):
    """m/min at which the VO2 cost equals v_o2 (inverse of vo2())."""
    a, b, c = 0.000104, 0.182258, -4.6 - v_o2
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def race_time(vd, dist_m):
    """Seconds to race dist_m at VDOT vd (bisection on duration)."""
    lo, hi = dist_m / 1000 * 60 * 1.5, dist_m / 1000 * 60 * 15      # 1:30/km .. 15:00/km in seconds
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot(dist_m, mid) > vd:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def kmh_at_fraction(vd, f):
    return speed_for_vo2(vd * f) * 60 / 1000


def vdot_from_threshold_kmh(kmh):
    """VDOT implied by a threshold (T) pace: T = 88 % of VDOT."""
    return vo2(kmh * 1000 / 60) / FRACTIONS["T"]


def paces(vd):
    """Training paces in km/h: {E: (slow, fast), M, T, I, R}."""
    return {
        "E": (kmh_at_fraction(vd, FRACTIONS["E_slow"]), kmh_at_fraction(vd, FRACTIONS["E_fast"])),
        "M": DISTANCES["Marathon"] / race_time(vd, DISTANCES["Marathon"]) * 3.6,
        "T": kmh_at_fraction(vd, FRACTIONS["T"]),
        "I": kmh_at_fraction(vd, FRACTIONS["I"]),
        "R": MILE / race_time(vd, MILE) * 3.6 / R_FACTOR,
    }


def riegel(time_s, d1, d2, k=1.06):
    return time_s * (d2 / d1) ** k


STANDARD = ["1500m", "Mile", "3000m", "5K", "10K", "10 miles", "Half marathon", "Marathon"]


def equivalents(vd, events=STANDARD, race_gain=0.0):
    """{event: seconds} at VDOT vd. race_gain > 0 speeds every result up (e.g. 0.025 for super shoes)."""
    return {e: race_time(vd, DISTANCES[e]) / (1 + race_gain) for e in events}


def table(vd, unit="km", race_gain=0.0):
    p = paces(vd)
    lines = [f"VDOT {vd:.1f}", "", "Training paces (per " + unit + ")"]
    lines.append(f"  E  easy / long    {pace(p['E'][1], unit)}-{pace(p['E'][0], unit)}  (HR below LT1 governs)")
    for k, label in (("M", "marathon"), ("T", "threshold"), ("I", "interval"), ("R", "repetition")):
        lines.append(f"  {k}  {label:<14} {pace(p[k], unit)}")
    lines += ["", "Race equivalents" + (f" (+{race_gain * 100:.1f} % race-shoe gain)" if race_gain else "")]
    for e, s in equivalents(vd, race_gain=race_gain).items():
        lines.append(f"  {e:<14} {hms(s):>8}   {pace(DISTANCES[e] / s * 3.6, unit)}/{unit}")
    return "\n".join(lines)
