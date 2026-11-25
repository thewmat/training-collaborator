"""Install, remove or show the background job that runs `runlab auto` every N minutes.

macOS: a LaunchAgent (~/Library/LaunchAgents). Linux: a crontab line. Windows: a Task Scheduler task.
The job runs on this computer while it is on and logged in; output goes to me/out/auto.log.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

from . import config


def _tag():
    return hashlib.sha1(config.ROOT.encode()).hexdigest()[:8]


def label():
    return f"com.runlab.auto.{_tag()}"


def _args(claude=False):
    return [sys.executable, "-m", "runlab", "auto", "--quiet", "--notify"] + (["--claude"] if claude else [])


def _log():
    return config.out("auto.log")


def cron_spec(every):
    if every < 60:
        return f"*/{every} * * * *"
    h = max(1, round(every / 60))
    return "0 * * * *" if h == 1 else f"0 */{h} * * *"


def _q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def cron_line(every, claude=False):
    cmd = " ".join(_q(a) for a in _args(claude))
    return f"{cron_spec(every)} cd {_q(config.ROOT)} && {cmd} >> {_q(_log())} 2>&1  # runlab-auto {_tag()}"


def plist(every, claude=False):
    args = "".join(f"<string>{a}</string>" for a in _args(claude))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label()}</string>
  <key>ProgramArguments</key><array>{args}</array>
  <key>WorkingDirectory</key><string>{config.ROOT}</string>
  <key>StartInterval</key><integer>{every * 60}</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{_log()}</string>
  <key>StandardErrorPath</key><string>{_log()}</string>
</dict></plist>
"""


def _plist_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/{label()}.plist")


def win_cmd(claude=False):
    args = " ".join(f'"{a}"' if " " in a else a for a in _args(claude))
    return f'@echo off\r\ncd /d "{config.ROOT}"\r\n{args} >> "{_log()}" 2>&1\r\n'


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def install(every=30, claude=False, dry_run=False):
    every = max(15, min(int(every), 720))
    if sys.platform == "darwin":
        if dry_run:
            return f"would write {_plist_path()}:\n{plist(every, claude)}"
        os.makedirs(os.path.dirname(_plist_path()), exist_ok=True)
        _run(["launchctl", "unload", _plist_path()])
        open(_plist_path(), "w").write(plist(every, claude))
        r = _run(["launchctl", "load", "-w", _plist_path()])
        if r.returncode:
            raise SystemExit(f"launchctl failed: {r.stderr.strip()}")
        return f"installed LaunchAgent {label()}: every {every} min"
    if sys.platform.startswith("win"):
        wrapper = config.path("auto.cmd")
        tn = f"runlab-auto-{_tag()}"
        if dry_run:
            return f"would write {wrapper}:\n{win_cmd(claude)}\nand run: schtasks /Create /F /SC MINUTE /MO {every} /TN {tn} /TR \"{wrapper}\""
        open(wrapper, "w").write(win_cmd(claude))
        r = _run(["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(every), "/TN", tn, "/TR", f'"{wrapper}"'])
        if r.returncode:
            raise SystemExit(f"schtasks failed: {r.stderr.strip() or r.stdout.strip()}")
        return f"installed scheduled task {tn}: every {every} min"
    if not shutil.which("crontab"):
        raise SystemExit("crontab not found: install cron, or keep `python3 -m runlab watch` running")
    line = cron_line(every, claude)
    if dry_run:
        return f"would add to crontab:\n{line}"
    cur = _run(["crontab", "-l"]).stdout
    keep = [ln for ln in cur.splitlines() if f"runlab-auto {_tag()}" not in ln]
    r = _run(["crontab", "-"], input="\n".join(keep + [line]) + "\n")
    if r.returncode:
        raise SystemExit(f"crontab failed: {r.stderr.strip()}")
    return f"installed cron job: every {every} min"


def remove():
    if sys.platform == "darwin":
        if os.path.exists(_plist_path()):
            _run(["launchctl", "unload", "-w", _plist_path()])
            os.remove(_plist_path())
            return "removed LaunchAgent"
        return "nothing installed"
    if sys.platform.startswith("win"):
        r = _run(["schtasks", "/Delete", "/F", "/TN", f"runlab-auto-{_tag()}"])
        return "removed scheduled task" if r.returncode == 0 else "nothing installed"
    if not shutil.which("crontab"):
        return "nothing installed"
    cur = _run(["crontab", "-l"]).stdout
    keep = [ln for ln in cur.splitlines() if f"runlab-auto {_tag()}" not in ln]
    if len(keep) == len(cur.splitlines()):
        return "nothing installed"
    _run(["crontab", "-"], input="\n".join(keep) + ("\n" if keep else ""))
    return "removed cron job"


def status():
    if sys.platform == "darwin":
        job = f"LaunchAgent {label()}" if os.path.exists(_plist_path()) else None
    elif sys.platform.startswith("win"):
        job = f"task runlab-auto-{_tag()}" if _run(["schtasks", "/Query", "/TN", f"runlab-auto-{_tag()}"]).returncode == 0 else None
    else:
        cur = _run(["crontab", "-l"]).stdout if shutil.which("crontab") else ""
        job = next((ln for ln in cur.splitlines() if f"runlab-auto {_tag()}" in ln), None)
    lines = [f"job        {job or 'not installed (python3 -m runlab schedule install)'}"]
    st = config.data("auto.json")
    if os.path.exists(st):
        s = json.load(open(st))
        lines.append(f"last pass  {s.get('last_pass', '-')}  ({len(s.get('seen') or [])} runs on record"
                     + (f", waiting for FIT: {', '.join(s['waiting_for_fit'])}" if s.get("waiting_for_fit") else "") + ")")
    if os.path.exists(_log()):
        tail = open(_log(), errors="replace").read().strip().splitlines()[-5:]
        if tail:
            lines += ["log tail"] + [f"  {t}" for t in tail]
    return "\n".join(lines)
