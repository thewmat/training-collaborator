"""Official personal bests from public results, kept in me/pbs.json.

Public results sites differ by country (see the find-pbs skill): UK Power of 10 / runbritain,
parkrun, World Athletics, national federation databases, Athlinks and race timing sites.
Many require a sign-in or block automated requests, so the reliable route is:
  1. Claude finds the athlete's profile page (the athlete supplies their name and club),
  2. reads it in a browser or the athlete pastes the page text,
  3. `python3 -m runlab pbs import FILE` parses it here.

The parser reads any text where a line holds an event name and a time, e.g. a Power of 10
'Best known performances' table or a pasted results list:
  10K   41:30   ...   Riverside 10K         3 May 26
  HM    1:32:10 ...   Hilltown Half         12 Oct 25
For each event the fastest time wins. Dates are parsed when present (d Mon yy / yyyy-mm-dd / dd/mm/yyyy).
"""
import datetime as dt
import json
import os
import re

from . import config, vdot
from .units import DISTANCES, event_name, hms, parse_time

TIME = re.compile(r"(?<![\d:.])(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,2})?)(?![\d:])")
DATE = [(re.compile(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{2,4})\b"), "dmy_name"),
        (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
        (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "dmy")]
EVENT_TOKENS = sorted(set(list(DISTANCES) + ["HM", "Mar", "5M", "10M", "Half", "Mile", "1M", "parkrun",
                                             "5km", "10km", "3000", "5000", "10000", "1500", "800", "400", "20M"]),
                      key=len, reverse=True)
EVENT_RE = re.compile(r"(?i)^\s*(" + "|".join(re.escape(t) for t in EVENT_TOKENS) + r")\b")


def _date(line):
    for rx, kind in DATE:
        m = rx.search(line)
        if not m:
            continue
        try:
            if kind == "dmy_name":
                y = int(m.group(3)); y += 2000 if y < 100 else 0
                return dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {y}", "%d %b %Y").date().isoformat()
            if kind == "iso":
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            continue
    return None


def parse(text, source=""):
    found = {}
    for raw in text.splitlines():
        line = raw.replace("\t", "  ")
        m = EVENT_RE.match(line)
        if not m:
            continue
        ev = event_name(m.group(1)) or event_name(m.group(1).upper())
        if not ev:
            continue
        times = TIME.findall(line[m.end():])
        if not times:
            continue
        secs = parse_time(times[0])
        rec = {"event": ev, "time": times[0], "time_s": secs, "date": _date(line), "source": source,
               "line": raw.strip()[:160]}
        if ev not in found or secs < found[ev]["time_s"]:
            found[ev] = rec
    return list(found.values())


def path():
    return config.path("pbs.json")


def load():
    return json.load(open(path())) if os.path.exists(path()) else []


def save(rows):
    os.makedirs(config.home(), exist_ok=True)
    json.dump(sorted(rows, key=lambda r: DISTANCES.get(r["event"], 0)), open(path(), "w"), indent=1)


def merge(new):
    cur = {r["event"]: r for r in load()}
    changed = []
    for r in new:
        old = cur.get(r["event"])
        if not old or r["time_s"] < old["time_s"]:
            cur[r["event"]] = r
            changed.append(r["event"])
    save(list(cur.values()))
    return changed


def add(event, time, date=None, venue="", source="manual"):
    ev = event_name(event)
    if not ev:
        raise SystemExit(f"unknown event {event!r}; use one of {', '.join(DISTANCES)}")
    return merge([{"event": ev, "time": time, "time_s": parse_time(time), "date": date, "venue": venue, "source": source}])


def text(rows=None):
    rows = rows if rows is not None else load()
    if not rows:
        return "No PBs stored yet. Use the find-pbs skill, or: python3 -m runlab pbs add 10K 41:30 --date 2026-05-03"
    lines = ["event          time       VDOT   date        source"]
    for r in sorted(rows, key=lambda r: DISTANCES.get(r["event"], 0)):
        v = vdot.vdot(DISTANCES[r["event"]], r["time_s"]) if DISTANCES.get(r["event"], 0) >= 1500 else None
        lines.append(f"{r['event']:<14} {hms(r['time_s'], frac='.' in r['time']):>9}  {v and round(v, 1) or '-':>5}  "
                     f"{r.get('date') or '-':<10}  {r.get('source', '')[:40]}")
    return "\n".join(lines)
