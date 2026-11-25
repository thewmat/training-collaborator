"""One-page HTML dashboard (inline SVG, no external scripts): me/out/dashboard.html.

Reads the JSON the other commands write (curve, bests, history, readiness, PBs) and draws:
  1. headline sentence and four numbers: threshold pace, easy pace, VDOT, 4-week change
  2. fitness curve over time: pace at LT2 and LT1 HR per 30-day window (up = faster)
  3. this month's runs: pace against HR with the fitted line, and the line from 4 weeks earlier
  4. race estimates and training paces
  5. weekly volume, best performances, PBs, readiness
"""
import datetime as dt
import html
import json
import os

from . import config, vdot
from .units import DISTANCES, hms, pace

CSS = """
:root{--bg:#fbfaf8;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e6e3de;--a:#d1495b;--b:#2e86ab;--c:#8a8a8f;--good:#2a9d4b;--warn:#d99a00;--bad:#c8323c}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141416;--card:#1d1d20;--ink:#f2f2f3;--mute:#a1a1a8;--line:#323237;--a:#ef6f7f;--b:#5cb4dc;--c:#77777d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 12px}
.sub{color:var(--mute);margin:0 0 20px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}.kpi b{display:block;font-size:24px;font-variant-numeric:tabular-nums}
.kpi span{color:var(--mute);font-size:13px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);font-size:14px}th{color:var(--mute);font-weight:500}
.note{color:var(--mute);font-size:13px;margin:8px 0 0}svg{width:100%;height:auto;display:block}svg text{fill:var(--mute);font-size:11px}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;color:#fff;font-weight:600}.Green{background:var(--good)}.Amber{background:var(--warn)}.Red{background:var(--bad)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:16px}
.scroll{overflow-x:auto}.card h2+.scroll,.scroll+h2{margin-top:16px}
"""


def _load(name):
    p = config.out(name)
    return json.load(open(p)) if os.path.exists(p) else None


def _esc(s):
    return html.escape(str(s))


def line_chart(series, labels, invert=True, w=900, h=260, fmt=lambda v: pace(v)):
    """series: [(name, colour_var, [values or None])]; labels: x labels. Values in km/h; up = faster."""
    vals = [v for _, _, s in series for v in s if v]
    if len(vals) < 2:
        return "<p class=note>Not enough data yet.</p>"
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.15 or 0.5
    lo, hi = lo - pad, hi + pad
    L, R, T, B = 52, 12, 12, 28
    x = lambda i: L + (w - L - R) * (i / max(1, len(labels) - 1))
    y = lambda v: T + (h - T - B) * ((hi - v) / (hi - lo))
    out = [f'<svg viewBox="0 0 {w} {h}" role="img">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        out.append(f'<line x1="{L}" x2="{w - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--line)"/>'
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{fmt(v)}</text>')
    step = max(1, len(labels) // 8)
    for i, lab in enumerate(labels):
        if i % step == 0 or i == len(labels) - 1:
            out.append(f'<text x="{x(i):.1f}" y="{h - 8}" text-anchor="middle">{_esc(lab)}</text>')
    for name, col, s in series:
        pts = [(x(i), y(v)) for i, v in enumerate(s) if v]
        out.append('<polyline fill="none" stroke="var(%s)" stroke-width="2.5" points="%s"/>'
                   % (col, " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)))
        for a, b in pts:
            out.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.5" fill="var({col})"/>')
        if pts:
            out.append(f'<text x="{pts[-1][0] - 4:.1f}" y="{pts[-1][1] - 9:.1f}" text-anchor="end" '
                       f'style="fill:var({col});font-weight:600">{_esc(name)} {fmt(s[-1] or 0)}</text>')
    out.append("</svg>")
    return "".join(out)


def scatter(points, lines, lt1, lt2, w=900, h=300):
    if not points:
        return "<p class=note>No points in the window.</p>"
    hrs = [p["hr"] for p in points] + [lt1, lt2]
    ks = [p["kmh"] for p in points]
    x0, x1 = min(hrs) - 4, max(hrs) + 4
    y0, y1 = min(ks) - 0.6, max(ks) + 0.6
    L, R, T, B = 52, 12, 12, 30
    x = lambda v: L + (w - L - R) * (v - x0) / (x1 - x0)
    y = lambda v: T + (h - T - B) * (y1 - v) / (y1 - y0)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img">']
    for k in range(5):
        v = y0 + (y1 - y0) * k / 4
        out.append(f'<line x1="{L}" x2="{w - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--line)"/>'
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{pace(v)}</text>')
    for hr, lab in ((lt1, "LT1"), (lt2, "LT2")):
        out.append(f'<line x1="{x(hr):.1f}" x2="{x(hr):.1f}" y1="{T}" y2="{h - B}" stroke="var(--c)" stroke-dasharray="4 4"/>'
                   f'<text x="{x(hr):.1f}" y="{h - 10}" text-anchor="middle">{lab} {hr}</text>')
    for name, col, a, b in lines:
        out.append(f'<line x1="{x(x0):.1f}" y1="{y(a + b * x0):.1f}" x2="{x(x1):.1f}" y2="{y(a + b * x1):.1f}" '
                   f'stroke="var({col})" stroke-width="2"/>')
    for p in points:
        r = 2.5 + min(p["min"], 15) / 3
        out.append(f'<circle cx="{x(p["hr"]):.1f}" cy="{y(p["kmh"]):.1f}" r="{r:.1f}" fill="var(--a)" fill-opacity=".35">'
                   f'<title>{_esc(p["date"])} {_esc(p["name"])}: {pace(p["kmh"])}/km at {p["hr"]:.0f} bpm, {p["min"]:.0f} min</title></circle>')
    out.append("</svg>")
    return "".join(out)


def bars(weeks, w=900, h=180):
    if not weeks:
        return ""
    m = max(x["km"] for x in weeks) or 1
    L, B, T = 40, 24, 10
    bw = (w - L - 8) / len(weeks)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img">']
    for k in range(4):
        v = m * k / 3
        yy = T + (h - T - B) * (1 - v / m)
        out.append(f'<line x1="{L}" x2="{w - 8}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="var(--line)"/><text x="{L - 6}" y="{yy + 4:.1f}" text-anchor="end">{v:.0f}</text>')
    for i, x_ in enumerate(weeks):
        bh = (h - T - B) * x_["km"] / m
        out.append(f'<rect x="{L + i * bw + 1:.1f}" y="{h - B - bh:.1f}" width="{bw - 2:.1f}" height="{bh:.1f}" rx="2" fill="var(--b)">'
                   f'<title>w/c {_esc(x_["week"])}: {x_["km"]:.1f} km, {x_["runs"]} runs, long {x_["long_km"]:.1f} km</title></rect>')
        if i % max(1, len(weeks) // 8) == 0:
            out.append(f'<text x="{L + i * bw + bw / 2:.1f}" y="{h - 6}" text-anchor="middle">{_esc(x_["week"][5:])}</text>')
    out.append("</svg>")
    return "".join(out)


def _auto_line():
    import os
    p = config.out("inbox.md")
    n = sum(1 for ln in open(p) if ln.startswith("- [ ]")) if os.path.exists(p) else 0
    return f" {n} run{'s' if n != 1 else ''} waiting for a verdict." if n else ""


def build():
    prof = config.profile()
    c, b, hist, rd = _load("curve.json"), _load("bests.json"), _load("history.json"), _load("readiness.json")
    from . import pbs as pbs_mod
    pbs = pbs_mod.load()
    name = prof.get("name") or "Runner"
    H = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>Training Dashboard</title><style>{CSS}</style></head><body><main>",
         f"<h1>{_esc(name)}: training dashboard</h1><p class=sub>Built {dt.datetime.now():%d %b %Y %H:%M} from Garmin data."
         + _auto_line() + "</p>"]
    if c and c.get("current"):
        k = c["current"]
        ch = k["change_4wk_s_km"]
        H.append(f"<div class=card><b>{_esc(c['headline'])}</b></div><div class=kpis>"
                 f"<div class=kpi><span>Threshold pace (HR {c['thresholds']['lt2']})</span><b>{k['pace_lt2']}/km</b></div>"
                 f"<div class=kpi><span>Easy pace (HR under {c['thresholds']['lt1']})</span><b>{k['easy_band']}</b></div>"
                 f"<div class=kpi><span>VDOT</span><b>{k['vdot']}</b></div>"
                 f"<div class=kpi><span>4-week change</span><b>{'faster' if ch < 0 else 'slower'} {abs(ch):.0f} s/km</b></div></div>")
        tr = c["trend"]
        if any(t["hr_confidence"] == "strap" for t in tr):     # wrist-HR windows are not comparable: hide them
            tr = [t for t in tr if t["hr_confidence"] == "strap"]
        H.append("<div class=card><h2>Fitness curve: pace at a fixed heart rate</h2>"
                 + line_chart([("LT2", "--a", [None if t["extrapolated"] else t["kmh_lt2"] for t in tr]),
                               ("LT1", "--b", [t["kmh_lt1"] for t in tr])],
                              [t["end"][5:] for t in tr])
                 + "<p class=note>Each point is the 30 days to that date. Higher = faster at the same heart rate = fitter. "
                   "Gaps in the LT2 line are windows with too little running near threshold heart rate to read it. "
                   "Only chest-strap windows are drawn once strap data exists."
                   + (f" Best on record: {c['best']['pace_lt2']}/km (30 days to {c['best']['end']})." if c.get("best") else "")
                 + "</p></div>")
        prev = next((t for t in reversed(tr) if t["end"] <= (dt.date.fromisoformat(tr[-1]["end"]) - dt.timedelta(27)).isoformat()), None)
        lines = [("now", "--a", k["a"], k["b"])]
        H.append("<div class=card><h2>This window's runs: pace against heart rate</h2>"
                 + scatter(k["points"], lines, c["thresholds"]["lt1"], c["thresholds"]["lt2"])
                 + f"<p class=note>{k['n']} steady laps and runs ({_esc(k['window'])}), HR {_esc(k['hr_confidence'])}. "
                   "Bigger dots = longer efforts. The line is read at LT1 and LT2."
                 + (f" Four weeks earlier LT2 pace was {prev['pace_lt2']}/km." if prev else "") + "</p></div>")
        gain = k.get("race_gain") or 0
        est = "".join(f"<tr><td>{_esc(e)}</td><td>{hms(s)}</td><td>{pace(DISTANCES[e] / s * 3.6)}/km</td></tr>"
                      for e, s in k["estimates"].items() if e in ("5K", "10K", "10 miles", "Half marathon", "Marathon"))
        p = vdot.paces(k["vdot"])
        tp = "".join(f"<tr><td>{a}</td><td>{v}</td></tr>" for a, v in (
            ("Easy / long", f"{pace(p['E'][1])}-{pace(p['E'][0])} (HR under {c['thresholds']['lt1']} governs)"),
            ("Marathon (M)", pace(p["M"])), ("Threshold (T)", pace(p["T"])), ("Interval (I)", pace(p["I"])), ("Repetition (R)", pace(p["R"]))))
        H.append(f"<div class=grid2><div class=card><h2>Race estimates (VDOT {k['vdot']})</h2><table>{est}</table>"
                 f"<p class=note>{'Includes a ' + format(gain * 100, '.1f') + ' % super-shoe allowance. ' if gain else ''}"
                 "Estimates assume training for the distance; the marathon needs the long runs to match.</p></div>"
                 f"<div class=card><h2>Daniels training paces</h2><table>{tp}</table></div></div>")
        from . import daniels
        lt1v = c["thresholds"]["lt1"]
        zr = "".join(f"<tr><td>{_esc(r['zone'])}</td><td>{r['pct_vo2'] * 100:.0f}</td><td>{pace(r['kmh'])}</td>"
                     f"<td>{round(r['hr']) if r['hr'] else '-'}</td><td>{hms(r['time_s']) if r['time_s'] else ''}</td></tr>"
                     for r in daniels.zone_grid(k["vdot"], c["thresholds"]["max"], prof["hr"].get("rest")))
        sp = "".join(f"<tr><td>{_esc(lab)}</td>" + "".join(f"<td>{hms(s, frac=d < 400)}</td>" for d, s in row.items()
                                                           if d in (200, 400, 800, 1000, 1600)) + "</tr>"
                     for lab, row in daniels.split_table(k["vdot"]).items())
        tt = "".join(f"<td>{m}'<br>{pace(v)}</td>" for m, v, _ in daniels.tempo_table(k["vdot"]))
        H.append(f"<div class=grid2><div class=card><h2>Daniels zone grid</h2><div class=scroll><table><tr><th>Zone</th><th>%VO2max</th>"
                 f"<th>/km</th><th>HR (% max)</th><th>Race</th></tr>{zr}</table></div><p class=note>HR here is Daniels' generic % of "
                 f"max HR; your measured caps win (easy under {lt1v}).</p></div>"
                 f"<div class=card><h2>Rep times</h2><div class=scroll><table><tr><th></th><th>200</th><th>400</th><th>800</th><th>1000</th>"
                 f"<th>1600</th></tr>{sp}</table></div><h2>Continuous tempo by duration</h2><div class=scroll><table><tr>{tt}</tr></table></div></div></div>")
    if rd and rd.get("has_data"):
        H.append(f"<div class=card><h2>Readiness {_esc(rd['date'])} <span class='pill {rd['verdict']}'>{rd['verdict']}</span></h2>"
                 f"<p>{_esc(rd['action'])}</p><p class=note>{_esc('; '.join(rd['reasons']) or 'No flag raised.')}</p></div>")
    if hist:
        wk = hist["weeks"][-26:]
        H.append("<div class=card><h2>Weekly running volume (km)</h2>" + bars(wk)
                 + f"<p class=note>{hist['runs']} runs, {hist['total_km']:,} km since {hist['first_run']}.</p></div>")
    if pbs:
        rows = "".join(f"<tr><td>{_esc(r['event'])}</td><td>{_esc(r['time'])}</td><td>{_esc(r.get('date') or '-')}</td>"
                       f"<td>{round(vdot.vdot(DISTANCES[r['event']], r['time_s']), 1) if DISTANCES.get(r['event'], 0) >= 1500 else '-'}</td></tr>"
                       for r in sorted(pbs, key=lambda r: DISTANCES.get(r["event"], 0)))
        H.append(f"<div class=card><h2>Official personal bests</h2><table><tr><th>Event</th><th>Time</th><th>Date</th><th>VDOT</th></tr>{rows}</table></div>")
    if b and b.get("top_by_vdot"):
        rows = "".join(f"<tr><td>{_esc(p['event'])}</td><td>{hms(p['time_s'])}</td><td>{p['vdot']}</td><td>{_esc(p['date'])}</td>"
                       f"<td>{_esc(p['kind'])}</td></tr>" for p in b["top_by_vdot"][:8])
        H.append(f"<div class=card><h2>Best performances in Garmin data</h2><table><tr><th>Distance</th><th>Time</th><th>VDOT</th>"
                 f"<th>Date</th><th>Source</th></tr>{rows}</table><p class=note>Race = an activity marked or named as a race. "
                 "Effort = fastest segment inside a run.</p></div>")
    H.append("</main></body></html>")
    p = config.out("dashboard.html")
    open(p, "w").write("".join(H))
    return p
