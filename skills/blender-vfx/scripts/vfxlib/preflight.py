"""Startup preflight: what is actually installed and usable on this machine.

Every item is PASS, FAIL, UNKNOWN or NOT_APPLICABLE with a short detail. The
Cowork Linux VM and the native Mac are reported separately: the VM can read and
write the project folders but cannot run the Mac's Blender, Metal or MPS, so
those items are NOT_APPLICABLE there instead of quietly passing.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

from . import __version__
from .common import atomic_write
from .events import machine_kind

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.dirname(SCRIPTS)
REPO = os.path.dirname(os.path.dirname(SKILL))

DEFAULT_SETTINGS = {"mode": "filmmaker", "learning": "off", "research": "off", "budget": "balanced"}
ALLOWED = {"mode": {"filmmaker", "vfx-artist"}, "learning": {"off", "contextual", "guided"},
           "research": {"off", "on_failure", "session"}, "budget": {"economy", "balanced", "quality"}}


def machine_facts(blender=None):
    """Raw checks shared with `vfx.py doctor`."""
    problems, notes = [], []
    if sys.version_info < (3, 9):
        problems.append("Python 3.9+ needed")
    mods = {}
    for m in ("numpy", "cv2"):
        try:
            mod = __import__(m)
            mods[m] = getattr(mod, "__version__", "yes")
        except ImportError:
            mods[m] = None
    if not mods["numpy"] or not mods["cv2"]:
        notes.append("footage analysis and pixel checks need: pip install numpy opencv-python-headless")
    tools = {t: bool(shutil.which(t)) for t in ("ffmpeg", "ffprobe")}
    if not all(tools.values()):
        notes.append("video checks need ffmpeg and ffprobe on PATH")
    from .jobs import find_blender
    exe = find_blender(blender)
    bver = None
    if exe:
        try:
            r = subprocess.run([exe, "-b", "--version"], capture_output=True, text=True, timeout=60)
            bver = next((l.strip() for l in r.stdout.splitlines() if l.startswith("Blender")), None)
        except (OSError, subprocess.SubprocessError):
            bver = None
    if not bver:
        notes.append("Blender not found from the shell; set BLENDER=/path/to/blender for headless jobs")
    missing = [n for n in ("SKILL.md", "references", "recipes", "templates") if not os.path.exists(os.path.join(SKILL, n))]
    if missing:
        problems.append(f"skill files missing: {missing}")
    try:
        from . import state as st
        with tempfile.TemporaryDirectory() as t:
            st.init(t, "doctor")
            st.set_values(t, [("facts.ok", True)])
            if st.load(t)[0]["facts"]["ok"] is not True:
                problems.append("state write test failed")
    except Exception as e:  # report, don't crash
        problems.append(f"state write test failed: {e}")
    return {"mods": mods, "tools": tools, "blender": bver, "blender_path": exe, "problems": problems, "notes": notes,
            "missing": missing}


def engine_commit(repo=REPO):
    """Commit of the engine checkout, from .git without needing git, or from ENGINE_COMMIT."""
    g = os.path.join(repo, ".git")
    try:
        if os.path.isdir(g):
            with open(os.path.join(g, "HEAD")) as f:
                head = f.read().strip()
            if not head.startswith("ref:"):
                return head[:12]
            ref = head.split(" ", 1)[1].strip()
            rp = os.path.join(g, *ref.split("/"))
            if os.path.exists(rp):
                with open(rp) as f:
                    return f.read().strip()[:12]
            with open(os.path.join(g, "packed-refs")) as f:
                for line in f:
                    if line.strip().endswith(" " + ref):
                        return line.split()[0][:12]
        with open(os.path.join(repo, "ENGINE_COMMIT")) as f:
            return f.read().strip()[:12]
    except OSError:
        return None
    return None


def load_settings(root):
    s, src, err = dict(DEFAULT_SETTINGS), "defaults", None
    if root:
        p = os.path.join(root, "_studio", "config.json")
        if os.path.exists(p):
            try:
                with open(p) as f:
                    user = json.load(f)
                for k in DEFAULT_SETTINGS:
                    if k in user:
                        s[k] = user[k]
                src = p
            except (OSError, ValueError) as e:
                err = f"config unreadable: {e}"
    bad = [k for k, v in s.items() if v not in ALLOWED[k]]
    return s, src, err or (f"invalid values: {bad}" if bad else None)


def _profiles(root, shot):
    cands = []
    if shot:
        cands += [os.path.join(shot, "00_brief", "vfx-profile.md"), os.path.join(shot, "vfx-profile.md")]
    if root:
        cands.append(os.path.join(root, "_studio", "vfx-profile.md"))
    cands.append(os.path.join(os.path.expanduser("~"), ".config", "blender-vfx", "vfx-profile.md"))
    return [p for p in cands if os.path.isfile(p)]


def run(blender=None, root=None, shot=None, require_native=False):
    kind = machine_kind()
    f = machine_facts(blender)
    items = []

    def add(name, status, detail):
        items.append({"item": name, "status": status, "detail": detail})

    commit = engine_commit()
    add("engine", "FAIL" if f["missing"] else "PASS",
        {"version": __version__, "commit": commit or "unknown", "path": SCRIPTS, "missing": f["missing"]})
    native = kind == "mac"
    add("machine", "PASS" if native or not require_native else "FAIL",
        {"kind": kind, "platform": sys.platform, "os": platform.platform(), "arch": platform.machine(),
         "python": platform.python_version(), "python_path": sys.executable,
         "role": "renders, Blender, Metal and MPS run here" if native else
                 "file access only: cannot run the Mac's Blender, Metal or MPS" if kind == "cowork-vm" else "other"})
    if f["blender"]:
        add("blender", "PASS", {"version": f["blender"], "path": f["blender_path"]})
    elif kind == "cowork-vm":
        add("blender", "NOT_APPLICABLE", "Blender runs on the Mac; this is the Cowork VM")
    else:
        add("blender", "FAIL", f"not found or did not run ({f['blender_path'] or 'no path'}); pass --blender or set BLENDER")
    add("python_modules", "PASS" if all(f["mods"].values()) else "FAIL", f["mods"])
    add("ffmpeg", "PASS" if all(f["tools"].values()) else "FAIL", f["tools"])
    add("state_write_test", "FAIL" if any("state write" in p for p in f["problems"]) else "PASS",
        [p for p in f["problems"] if "state write" in p] or "temp shot written and read back")
    if shot:
        from . import events as ev
        try:
            lp = ev.paths(shot)["log"]
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            os.close(os.open(lp, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644))  # can append, writes nothing
            evs, _, bad = ev.read(shot)
            add("shot_events", "PASS" if not bad else "FAIL", {"shot": shot, "events": len(evs), "bad_lines": bad})
        except Exception as e:
            add("shot_events", "FAIL", f"cannot write the shot's event log: {e}")
    else:
        add("shot_events", "NOT_APPLICABLE", "no --shot given")
    profs = _profiles(root, shot)
    add("personal_overrides", "PASS" if profs else "UNKNOWN", profs or "no vfx-profile.md found; public defaults apply")
    settings, src, err = load_settings(root)
    add("settings", "FAIL" if err else "PASS", {"values": settings, "source": src, "error": err})
    from . import hardware
    m = hardware.detect()
    add("hardware", "PASS", {k: m.get(k) for k in ("tier", "ram_gb", "render_memory_gb", "gpus", "texture_res") if k in m})
    must = ["engine", "state_write_test", "settings"] + (["blender", "machine"] if native or require_native else [])
    ok = all(i["status"] == "PASS" for i in items if i["item"] in must)
    if shot and any(i["item"] == "shot_events" and i["status"] == "PASS" for i in items):
        from . import events as ev
        ev.append(shot, "note", source="preflight", summary=f"preflight on {kind}", status="PASS" if ok else "FAIL",
                  detail=[f"{i['item']}: {i['status']}" for i in items if i["status"] not in ("PASS", "NOT_APPLICABLE")] or None)
    return {"ok": ok, "machine": kind, "engine": __version__, "commit": commit, "time": round(time.time(), 1),
            "items": items}


def write_report(rep, root=None, path=None):
    if not path and root:
        path = os.path.join(root, "_studio", "preflight", f"{rep['machine']}.json")
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        atomic_write(path, json.dumps(rep, indent=1, default=str))
    return path
