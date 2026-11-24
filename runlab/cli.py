"""Command line: python3 -m runlab <command> [options]. Run with no command for the list."""
import argparse
import json
import os
import shutil
import sys

from . import config


def _vdot_arg(a):
    """VDOT from --vdot, --race 'EVENT TIME', or the current fitness curve."""
    from . import vdot as V
    from .units import DISTANCES, event_name, parse_time
    if getattr(a, "vdot", None):
        return float(a.vdot), "given"
    if getattr(a, "race", None):
        ev, t = a.race.rsplit(" ", 1)
        e = event_name(ev)
        if not e:
            raise SystemExit(f"unknown event {ev!r}")
        return V.vdot(DISTANCES[e], parse_time(t)), f"{e} {t}"
    p = config.out("curve.json")
    if os.path.exists(p):
        c = json.load(open(p))
        if c.get("current"):
            return c["current"]["vdot"], f"fitness curve ({c['current']['window']})"
    raise SystemExit("no VDOT: pass --vdot 55, --race '10K 40:00', or run: python3 -m runlab curve")


def cmd_init(a):
    src, dst = os.path.join(config.ROOT, "me.example"), config.home()
    os.makedirs(dst, exist_ok=True)
    made = []
    for root, _, files in os.walk(src):
        for f in files:
            s = os.path.join(root, f)
            d = os.path.join(dst, os.path.relpath(s, src))
            if not os.path.exists(d):
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy(s, d)
                made.append(os.path.relpath(d, config.ROOT))
    env = os.path.join(config.ROOT, ".env")
    if not os.path.exists(env):
        shutil.copy(os.path.join(config.ROOT, ".env.example"), env)
        made.append(".env")
    print("created: " + (", ".join(made) or "nothing (already set up)"))
    print(f"workspace: {dst}  (gitignored)")


def cmd_doctor(a):
    prof = config.profile()
    print(f"workspace     {config.home()}  {'ok' if os.path.exists(config.path('profile.json')) else 'MISSING: run init'}")
    lt1, lt2, mx, how = config.thresholds(prof)
    print(f"thresholds    LT1 {lt1} LT2 {lt2} max {mx} ({how})")
    print(f"Garmin key    {'set' if os.environ.get('GARMIN_PERSONAL_API_KEY') else 'NOT SET (docs/garmin-setup.md)'}")
    from . import garmin
    acts = garmin.load("activities.json")
    import glob
    print(f"data          {len(acts)} activities, {len(glob.glob(config.data('fit', '*.fit')))} FIT files")
    if os.environ.get("GARMIN_PERSONAL_API_KEY") and not a.offline:
        print("connection    " + json.dumps(garmin.check()))


def cmd_sync(a):
    from . import garmin
    garmin.sync(history_days=a.days, fit_days=a.fit_days, all_fits=a.all_fits)


def cmd_import(a):
    from . import garmin
    garmin.import_export(a.path)


def cmd_fit(a):
    from . import garmin
    garmin.fetch_fits(a.ids)
    print("ok")


def cmd_review(a):
    from . import analyse
    path = analyse.latest_fit() if a.id in (None, "latest") else analyse.find_fit(a.id)
    r = analyse.analyse(path, a.official, 1609.344 if a.miles else 1000.0, a.lap)
    if a.json:
        print(json.dumps(r, indent=1))
    else:
        print(analyse.report(r))


def cmd_compare(a):
    from . import analyse
    from .units import pace
    r = analyse.compare_matched(analyse.find_fit(a.a), analyse.find_fit(a.b), bin_min=a.bin)
    print(f"Matched on cumulative work time (first 150 s of each rep dropped). HR: A {r['hr_quality'][0]}, B {r['hr_quality'][1]}")
    print("work min     A pace @ HR        B pace @ HR")
    for x in r["rows"]:
        fa = f"{pace(x['a']['kmh'])} @ {x['a']['hr']}" if x["a"]["kmh"] else "-"
        fb = f"{pace(x['b']['kmh'])} @ {x['b']['hr']}" if x["b"]["kmh"] else "-"
        print(f"{x['from_min']:>3}-{x['to_min']:<3}    {fa:<18} {fb}")


def cmd_curve(a):
    from . import curve
    c = curve.build(a.asof, a.weeks, a.refresh)
    print(json.dumps(c["current"], indent=1) if a.json else curve.text(c))


def cmd_estimate(a):
    from . import vdot as V
    vd, src = _vdot_arg(a)
    prof = config.profile()
    gain = prof["racing"]["plate_gain"] if prof["racing"].get("super_shoes") and src.startswith("fitness") else 0.0
    print(f"source: {src}")
    print(V.table(vd, prof.get("units", "km"), gain))


def cmd_workouts(a):
    from . import workouts
    vd, src = _vdot_arg(a)
    lt1, lt2, _, _ = config.thresholds()
    km = a.km
    if not km:
        from . import garmin
        import datetime as dt
        runs = [x for x in garmin.load("activities.json") if garmin.is_run(x)
                and x["startTimeLocal"][:10] >= (dt.date.today() - dt.timedelta(28)).isoformat()]
        km = sum((x.get("distance") or 0) for x in runs) / 1000 / 4 or 40
    print(f"source: {src}")
    print(workouts.text(vd, km, lt1, lt2, a.system or (config.profile()["preferences"].get("system") or "daniels").split()[0].lower(),
                        config.profile().get("units", "km")))


def cmd_bests(a):
    from . import bests
    print(bests.text(bests.assemble(a.refresh)))


def cmd_pbs(a):
    from . import pbs
    if a.action == "add":
        print("updated: " + (", ".join(pbs.add(a.event, a.time, a.date, a.venue or "", a.source or "manual")) or "no change"))
    elif a.action == "import":
        text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8", errors="replace").read()
        rows = pbs.parse(text, a.source or os.path.basename(a.file))
        print(pbs.text(rows))
        if not a.dry_run:
            print("updated: " + (", ".join(pbs.merge(rows)) or "no change"))
    print("\n" + pbs.text())


def cmd_history(a):
    from . import history
    h = history.build()
    print(open(config.out("history.md")).read() if not a.json else json.dumps(h, indent=1)[:20000])


def cmd_readiness(a):
    from . import readiness
    r = readiness.build(a.date, a.pain)
    json.dump(r, open(config.out("readiness.json"), "w"), indent=1)
    print(readiness.text(r))


def cmd_dashboard(a):
    from . import bests, curve, history, readiness, report
    for name, fn in (("curve", lambda: curve.build()), ("bests", bests.assemble), ("history", history.build),
                     ("readiness", lambda: json.dump(readiness.build(), open(config.out("readiness.json"), "w")))):
        try:
            fn()
        except SystemExit as e:
            print(f"{name}: skipped ({e})")
    print("wrote", report.build())


def cmd_demo(a):
    from . import demo
    home = os.path.abspath(a.dir)
    os.environ["RUNLAB_HOME"] = home
    demo.generate(home, weeks=a.weeks, seed=a.seed)
    print(f"synthetic athlete written to {home}")
    cmd_dashboard(a)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m runlab", description="Training collaborator toolkit")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("init", help="create the private workspace (me/) and .env"); s.set_defaults(f=cmd_init)
    s = sub.add_parser("doctor", help="check setup, key and data"); s.add_argument("--offline", action="store_true"); s.set_defaults(f=cmd_doctor)
    s = sub.add_parser("sync", help="pull Garmin data (incremental)")
    s.add_argument("--days", type=int, help="limit first pull to N days of activities (default: full history)")
    s.add_argument("--fit-days", type=int, default=120, help="download FIT files for runs in the last N days (default 120)")
    s.add_argument("--all-fits", action="store_true", help="download FIT for every run (slow; full best-performance search)")
    s.set_defaults(f=cmd_sync)
    s = sub.add_parser("import", help="import FIT files from a folder or Garmin export zip (no API key needed)")
    s.add_argument("path"); s.set_defaults(f=cmd_import)
    s = sub.add_parser("fit", help="download FIT files by Garmin activity id"); s.add_argument("ids", nargs="+"); s.set_defaults(f=cmd_fit)
    s = sub.add_parser("review", help="analyse one run (default: latest)")
    s.add_argument("id", nargs="?"); s.add_argument("--official", type=float, help="measured course distance in metres")
    s.add_argument("--lap", type=int, help="analyse one device lap only"); s.add_argument("--miles", action="store_true")
    s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_review)
    s = sub.add_parser("compare", help="compare two sessions matched on cumulative work time")
    s.add_argument("a"); s.add_argument("b"); s.add_argument("--bin", type=int, default=8); s.set_defaults(f=cmd_compare)
    s = sub.add_parser("curve", help="fitness curve: pace at LT1/LT2 HR over time")
    s.add_argument("--asof"); s.add_argument("--weeks", type=int, default=26); s.add_argument("--refresh", action="store_true")
    s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_curve)
    for name, fn, h in (("estimate", cmd_estimate, "VDOT race estimates"), ("paces", cmd_estimate, "Daniels training paces")):
        s = sub.add_parser(name, help=h); s.add_argument("--vdot", type=float); s.add_argument("--race", help="e.g. '10K 40:15'")
        s.set_defaults(f=fn)
    s = sub.add_parser("workouts", help="Daniels-based session library with pace bands and HR caps")
    s.add_argument("--vdot", type=float); s.add_argument("--race"); s.add_argument("--km", type=float, help="weekly km")
    s.add_argument("--system", choices=["daniels", "threshold", "marathon"]); s.set_defaults(f=cmd_workouts)
    s = sub.add_parser("bests", help="best performances from Garmin data"); s.add_argument("--refresh", action="store_true"); s.set_defaults(f=cmd_bests)
    s = sub.add_parser("pbs", help="official PBs: list | add EVENT TIME | import FILE")
    s.add_argument("action", choices=["list", "add", "import"]); s.add_argument("event", nargs="?"); s.add_argument("time", nargs="?")
    s.add_argument("--date"); s.add_argument("--venue"); s.add_argument("--source"); s.add_argument("--file", default="-")
    s.add_argument("--dry-run", action="store_true"); s.set_defaults(f=cmd_pbs)
    s = sub.add_parser("history", help="training history report"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_history)
    s = sub.add_parser("readiness", help="today's readiness verdict"); s.add_argument("--pain", type=int); s.add_argument("--date"); s.set_defaults(f=cmd_readiness)
    s = sub.add_parser("dashboard", help="rebuild everything and write me/out/dashboard.html"); s.set_defaults(f=cmd_dashboard)
    s = sub.add_parser("demo", help="generate a synthetic athlete and build its dashboard")
    s.add_argument("--dir", default=os.path.join(config.ROOT, "demo")); s.add_argument("--weeks", type=int, default=30)
    s.add_argument("--seed", type=int, default=7); s.set_defaults(f=cmd_demo)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return
    if a.cmd == "pbs" and a.action == "import" and a.event and a.file == "-":
        a.file = a.event
    a.f(a)


if __name__ == "__main__":
    main()
