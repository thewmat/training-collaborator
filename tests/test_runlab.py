"""Unit tests on synthetic data only. Run: python3 -m unittest -v"""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

HOME = tempfile.mkdtemp(prefix="runlab-test-")
os.environ["RUNLAB_HOME"] = HOME
os.environ.pop("GARMIN_PERSONAL_API_KEY", None)        # tests never touch Garmin

from runlab import (analyse, auto, bests, cli, config, curve, daniels, demo, history, pbs, readiness, report,  # noqa: E402
                    schedule, vdot, workouts)
from runlab.fit import decode, hr_source  # noqa: E402
from runlab.units import hms, parse_time  # noqa: E402


def setUpModule():
    demo.generate(HOME, weeks=20, seed=3)


def tearDownModule():
    shutil.rmtree(HOME, ignore_errors=True)


class TestVdot(unittest.TestCase):
    def test_published_table_values(self):
        self.assertAlmostEqual(vdot.vdot(5000, 19 * 60 + 57), 50.0, delta=0.1)
        p = vdot.paces(50)
        self.assertAlmostEqual(3600 / p["T"], 255, delta=1.5)        # 4:15/km
        self.assertAlmostEqual(3600 / p["I"], 235, delta=1.5)        # 3:55/km
        self.assertAlmostEqual(3600 / p["R"] * 0.4, 89, delta=1.0)   # 89 s per 400 m
        self.assertAlmostEqual(vdot.race_time(50, 10000), 41 * 60 + 21, delta=5)
        self.assertAlmostEqual(vdot.race_time(50, 42195), 3 * 3600 + 10 * 60 + 49, delta=20)

    def test_round_trip(self):
        for vd in (35, 50, 65, 80):
            for d in (1500, 5000, 21097.5, 42195):
                self.assertAlmostEqual(vdot.vdot(d, vdot.race_time(vd, d)), vd, places=3)

    def test_threshold_inverse(self):
        vd = 58.3
        self.assertAlmostEqual(vdot.vdot_from_threshold_kmh(vdot.paces(vd)["T"]), vd, places=3)

    def test_race_gain(self):
        a = vdot.equivalents(55)["10K"]
        b = vdot.equivalents(55, race_gain=0.025)["10K"]
        self.assertAlmostEqual(a / b, 1.025, places=6)


class TestUnits(unittest.TestCase):
    def test_times(self):
        self.assertEqual(parse_time("1:32:10"), 5530)
        self.assertEqual(parse_time("17:05.42"), 1025.42)
        self.assertEqual(hms(5530), "1:32:10")


class TestFit(unittest.TestCase):
    def test_decode_synthetic(self):
        acts = json.load(open(config.data("activities.json")))
        a = acts[-1]
        d = decode(analyse.find_fit(a["activityId"]))
        self.assertGreater(len(d["records"]), 100)
        self.assertAlmostEqual(d["session"]["dist_m"], a["distance"], delta=2)
        self.assertEqual(d["hr_source"], "strap")               # demo straps from week 9

    def test_wrist_before_strap(self):
        acts = json.load(open(config.data("activities.json")))
        d = decode(analyse.find_fit(acts[0]["activityId"]))
        self.assertEqual(d["hr_source"], "wrist")

    def test_hr_source_rules(self):
        self.assertEqual(hr_source([{"source": 3, "device_type": 1}]), "strap")        # BLE HR
        self.assertEqual(hr_source([{"source": 1, "device_type": 120}]), "strap")      # ANT+ HR
        self.assertEqual(hr_source([{"source": 1, "device_type": 124}]), "wrist")      # footpod only
        self.assertEqual(hr_source([{"source": 5, "device_type": 1, "product": 7}], (7,)), "wrist")


class TestReview(unittest.TestCase):
    def latest(self, name):
        acts = json.load(open(config.data("activities.json")))
        a = [x for x in acts if name in x["activityName"]][-1]
        return analyse.analyse(analyse.find_fit(a["activityId"])), a

    def test_reps_found(self):
        r, a = self.latest("x 1 km threshold")
        n = int(a["activityName"].split()[0])
        self.assertEqual(len(r["reps"]), n)
        for rep in r["reps"]:
            self.assertAlmostEqual(rep["dist_m"], 1000, delta=25)
            self.assertIsNotNone(rep["end_hr"])

    def test_cruise_reps(self):
        r, _ = self.latest("4 x 2 km cruise")
        self.assertEqual(len(r["reps"]), 4)

    def test_long_run_easy(self):
        r, _ = self.latest("Long run")
        self.assertEqual(r["reps"], [])
        self.assertLess(abs(r["drift_pct"]), 6)
        self.assertGreater(r["zones_s"]["below_lt1"], r["time_s"] * 0.9)

    def test_matched_compare(self):
        acts = [x for x in json.load(open(config.data("activities.json"))) if "cruise" in x["activityName"]]
        res = analyse.compare_matched(analyse.find_fit(acts[-4]["activityId"]), analyse.find_fit(acts[-1]["activityId"]), bin_min=6)
        self.assertTrue(res["rows"])
        # later session is fitter: faster pace in the matched bins
        self.assertGreater(res["rows"][0]["b"]["kmh"], res["rows"][0]["a"]["kmh"])


class TestCurve(unittest.TestCase):
    def test_curve_recovers_truth(self):
        c = curve.build(weeks=8, refresh=True)
        k = c["current"]
        self.assertEqual(k["hr_confidence"], "strap")
        # demo truth: threshold speed at week 19 of 20 is ~15.6 km/h -> ~3:51/km; allow lag/drift error
        self.assertAlmostEqual(k["kmh_lt2"], demo.v2_at(19, 20), delta=0.45)
        self.assertLess(k["change_4wk_s_km"], 0)                # improving
        self.assertIn("Threshold pace", c["headline"])


class TestBestsPbsHistory(unittest.TestCase):
    def test_bests(self):
        b = bests.assemble(refresh=True)
        self.assertIn("5K", b["by_event"])                      # parkruns are races
        self.assertTrue(all(p["kind"] == "race" for p in b["by_event"]["5K"]))
        self.assertTrue(b["top_by_vdot"])

    def test_pb_parse(self):
        text = "Event PB 2026\n5K 19:58 20:10 Hilltown 3 Mar 26\nHM\t1:32:10\nMar 3:15:00  2024-04-21\n800 2:21.4\nnonsense 12:00"
        rows = {r["event"]: r for r in pbs.parse(text, "test")}
        self.assertEqual(rows["5K"]["time_s"], 1198)
        self.assertEqual(rows["5K"]["date"], "2026-03-03")
        self.assertEqual(rows["Half marathon"]["time_s"], 5530)
        self.assertEqual(rows["Marathon"]["date"], "2024-04-21")
        self.assertIn("800m", rows)
        self.assertEqual(len(rows), 4)

    def test_pb_merge_keeps_fastest(self):
        pbs.merge([{"event": "10K", "time": "45:00", "time_s": 2700}])
        pbs.merge([{"event": "10K", "time": "46:00", "time_s": 2760}])
        self.assertEqual({r["event"]: r for r in pbs.load()}["10K"]["time_s"], 2700)

    def test_history(self):
        h = history.build()
        self.assertTrue(any(b["days"] >= 10 for b in h["breaks"]))   # the two-week break
        self.assertTrue(h["builds"])
        self.assertTrue(os.path.exists(config.out("history.md")))


class TestReadinessWorkoutsReport(unittest.TestCase):
    def test_readiness(self):
        r = readiness.build()
        self.assertIn(r["verdict"], ("Green", "Amber", "Red"))

    def test_workouts(self):
        lib = {s["key"]: s for s in workouts.library(55, 70, 150, 170)}
        self.assertIn("172", lib["cruise_1k"]["hr"])
        self.assertIn("150", lib["easy"]["hr"])
        t = 3600 / vdot.paces(55)["T"]
        fast, slow = (parse_time(x) for x in lib["cruise_mile"]["pace"].split("-"))
        self.assertTrue(fast <= t <= slow)

    def test_cli_and_dashboard(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["estimate", "--race", "10K 40:00"])
            cli.main(["dashboard"])
        self.assertIn("VDOT", buf.getvalue())
        html = open(config.out("dashboard.html")).read()
        self.assertIn("<svg", html)
        self.assertIn("Threshold pace", html)


if __name__ == "__main__":
    unittest.main()


class TestDaniels(unittest.TestCase):
    def workbook_pace(self, vd, pct_vo2):
        """Seconds per km from the inverse speed equation used in Daniels' tables."""
        x = vd * pct_vo2
        return 1000 / (29.54 + 5.000663 * x - 0.007546 * x * x) * 60

    def test_zone_grid_matches_workbook_formulas(self):
        g = {r["zone"]: r for r in daniels.zone_grid(50, hrmax=190, rest=50)}
        self.assertAlmostEqual(g["Recovery"]["pct_vo2"], 0.59, places=6)
        self.assertAlmostEqual(3600 / g["Recovery"]["kmh"], self.workbook_pace(50, 0.59), delta=1.0)
        self.assertAlmostEqual(3600 / g["Easy (high)"]["kmh"], self.workbook_pace(50, daniels.vo2_frac(0.75)), delta=1.0)
        self.assertAlmostEqual(g["Recovery"]["hr"], 0.65 * 190, places=6)
        self.assertAlmostEqual(g["Recovery"]["pct_hrr"], (0.65 * 190 - 50) / 140, places=6)
        self.assertEqual(g["Mile"]["pct_hr"], 1.0)
        self.assertAlmostEqual(g["5K"]["time_s"], vdot.race_time(50, 5000), places=6)
        e, m = 3600 / g["Easy (high)"]["kmh"], 3600 / g["Marathon"]["kmh"]
        self.assertAlmostEqual(3600 / g["Moderate aerobic"]["kmh"], e + (m - e) / 3, places=6)
        order = [r["kmh"] for r in daniels.zone_grid(50)]
        self.assertEqual(order, sorted(order))                       # every zone faster than the one before

    def test_tempo_and_splits(self):
        t = vdot.paces(50)["T"]
        tt = daniels.tempo_table(50)
        self.assertEqual(tt[0][1], t)
        self.assertAlmostEqual(tt[-1][1], t / 1.055, places=9)
        s = daniels.split_table(50)
        self.assertAlmostEqual(s["T"][1000], 3600 / t, places=6)
        self.assertAlmostEqual(s["R"][400], 89, delta=1.0)
        self.assertAlmostEqual(s["5K race"][1000], vdot.race_time(50, 5000) / 5, places=6)

    def test_points_and_heat(self):
        self.assertAlmostEqual(daniels.points_per_min(0.88), 0.683)
        self.assertAlmostEqual(daniels.points_per_min(0.89), (0.683 + 0.723) / 2, places=6)
        self.assertAlmostEqual(daniels.points_per_min(pct_hr=0.92), 0.683)
        self.assertEqual(daniels.points_per_min(0.3), 0.1)
        self.assertAlmostEqual(daniels.run_points([(600, daniels.kmh_at(50, 0.88), None)], 50), 6.83, places=2)
        self.assertEqual(daniels.heat_factor(15), 1.0)
        self.assertAlmostEqual(daniels.heat_factor((70 - 32) * 5 / 9), 1.015, places=6)
        self.assertEqual(daniels.level(120), "advanced high-school")

    def test_weekly_points_from_demo(self):
        rows = daniels.weekly_points(50, weeks=4)
        self.assertEqual(len(rows), 4)
        self.assertTrue(any(r["points"] > 30 for r in rows))

    def test_race_table_extended(self):
        evs = [e for e, *_ in daniels.race_table(50)]
        self.assertIn("15K", evs)
        self.assertIn("50K", evs)
        times = [t for _, t, *_ in daniels.race_table(50)]
        self.assertEqual(times, sorted(times))


class TestAuto(unittest.TestCase):
    def test_passes(self):
        for f in ("auto.json", "auto.lock"):
            if os.path.exists(config.data(f)):
                os.remove(config.data(f))
        r1 = auto.run()
        self.assertEqual(r1["new"], [])                              # first pass: baseline only
        st = json.load(open(config.data("auto.json")))
        last = sorted(st["seen"])[-1]
        st["seen"].remove(last)
        json.dump(st, open(config.data("auto.json"), "w"))
        r2 = auto.run()
        self.assertEqual([n["id"] for n in r2["new"]], [last])
        self.assertTrue(os.path.exists(config.out("inbox.md")))
        self.assertIn(last, open(config.out("inbox.md")).read())
        cur = json.load(open(config.path("profile.json")))["current"]
        self.assertIn("pace_lt2", cur)
        self.assertEqual(auto.run()["new"], [])                      # nothing new on the third pass
        self.assertEqual(auto.text(auto.run(), quiet=True), "")

    def test_lock(self):
        open(config.data("auto.lock"), "w").write("1")
        try:
            self.assertEqual(auto.run()["status"], "busy")
        finally:
            os.remove(config.data("auto.lock"))

    def test_schedule_specs(self):
        self.assertEqual(schedule.cron_spec(30), "*/30 * * * *")
        self.assertEqual(schedule.cron_spec(60), "0 * * * *")
        self.assertEqual(schedule.cron_spec(120), "0 */2 * * *")
        line = schedule.cron_line(30)
        self.assertIn("runlab auto --quiet --notify".replace(" ", "' '"), line)
        self.assertIn("# runlab-auto", line)
        self.assertIn("<integer>1800</integer>", schedule.plist(30))
