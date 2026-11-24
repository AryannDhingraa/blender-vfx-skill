#!/usr/bin/env python3
"""blender-vfx engine. One command, compact JSON out. Plain Python 3.9+.

  vfx.py doctor                                  install and machine check
  vfx.py status SHOT_DIR                         state, stale results, jobs (one call)
  vfx.py state init|show|set|done|reopen|record|check|invalidate|recover SHOT_DIR ...
  vfx.py analyse PLATE [--state SHOT_DIR]        camera move, blur, exposure, solve type
  vfx.py verify TARGET [--start N --end N]       frames or video: missing, corrupt, black, flicker
  vfx.py run JOB --state SHOT_DIR --blend F [--script S] [--frames 1-100 --pattern OUT/####.exr]
  vfx.py resume JOB --state SHOT_DIR             re-render only missing or broken frames
  vfx.py job JOB --state SHOT_DIR                status of a job (detects interrupted runs)
  vfx.py assets search "rusty barrel" --type model [--sheet _review/assets.jpg]
  vfx.py assets download ID --source polyhaven --type model --res 2k --dest 04_assets --approved
  vfx.py tidy PROJECT [--plan --clear-tmp --delete-duplicates]
  vfx.py package OUT.zip                         zip the skill for upload

Exit code 0 means checked and fine, 1 means a check failed, 2 means a usage or setup error.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from vfxlib import __version__  # noqa: E402
from vfxlib.common import out  # noqa: E402


def _val(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def cmd_doctor(a):
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
    from vfxlib.jobs import find_blender
    from vfxlib import hardware
    exe = find_blender(a.blender)
    bver = None
    if exe:
        try:
            r = subprocess.run([exe, "-b", "--version"], capture_output=True, text=True, timeout=60)
            bver = next((l.strip() for l in r.stdout.splitlines() if l.startswith("Blender")), None)
        except (OSError, subprocess.SubprocessError):
            bver = None
    if not bver:
        notes.append("Blender not found from the shell; set BLENDER=/path/to/blender for headless jobs")
    skill = os.path.dirname(HERE)
    need = ["SKILL.md", "references", "recipes", "templates"]
    missing = [n for n in need if not os.path.exists(os.path.join(skill, n))]
    if missing:
        problems.append(f"skill files missing: {missing}")
    try:
        import tempfile
        from vfxlib import state as st
        with tempfile.TemporaryDirectory() as t:
            st.init(t, "doctor")
            st.set_values(t, [("facts.ok", True)])
            if st.load(t)[0]["facts"]["ok"] is not True:
                problems.append("state write test failed")
    except Exception as e:  # report, don't crash
        problems.append(f"state write test failed: {e}")
    return out({"ok": not problems, "engine": __version__, "python": platform.python_version(),
                "platform": sys.platform, "modules": mods, "tools": tools, "blender": bver, "blender_path": exe,
                "machine": hardware.detect(), "problems": problems, "notes": notes}, 0 if not problems else 2)


def cmd_state(a):
    from vfxlib import state as st
    d = a.dir
    try:
        if a.op == "init":
            s = st.init(d, a.shot or os.path.basename(os.path.abspath(d)), a.mode)
            return out({"ok": True, "stage": s["stage"]})
        if a.op == "show":
            text = st.summary(d)
            if text is None:
                return out({"ok": False, "error": "no readable state; run state init"}, 2)
            print(text)
            return 0
        if a.op == "set":
            pairs = [(kv.split("=", 1)[0], _val(kv.split("=", 1)[1])) for kv in a.items]
            st.set_values(d, pairs)
            return out({"ok": True})
        if a.op == "done":
            s = st.done(d, a.items[0], a.note)
            return out({"ok": True, "next": s["stage"]})
        if a.op == "reopen":
            s = st.reopen(d, a.items[0])
            return out({"ok": True, "stage": s["stage"], "done": s["done"]})
        if a.op == "record":
            st.record(d, a.items[0], a.items[1:], a.deps or [], _val(a.params) if a.params else None)
            return out({"ok": True})
        if a.op == "check":
            s, _, problems = st.load(d)
            if s is None:
                return out({"ok": False, "error": "no readable state"}, 2)
            r = st.check(d, s, a.items[0], _val(a.params) if a.params else None)
            return out(r, 0 if r["valid"] else 1)
        if a.op == "invalidate":
            _, gone = st.invalidate(d, a.items[0])
            return out({"ok": True, "forgotten": gone})
        if a.op == "recover":
            s, src, problems = st.load(d)
            if s is None:
                return out({"ok": False, "error": "nothing to recover from"}, 2)
            if src != "current":
                st.commit(d, lambda x: None, f"recover from {src}")
            return out({"ok": True, "source": src, "stage": s["stage"]})
    except st.StateError as e:
        return out({"ok": False, "error": str(e)}, 2)
    except IndexError:
        return out({"ok": False, "error": f"state {a.op} needs more arguments"}, 2)


def cmd_status(a):
    from vfxlib import state as st, jobs
    text = st.summary(a.dir)
    lines = [text] if text else ["no state yet (vfx.py state init)"]
    jd = st.paths(a.dir)["jobs"]
    if os.path.isdir(jd):
        for f in sorted(os.listdir(jd)):
            if f.endswith(".json"):
                j = jobs.status(jd, f[:-5])
                extra = f" rerender {j['check'].get('rerender')}" if j.get("check", {}).get("rerender") else ""
                lines.append(f"job {j['job']}: {j['status']} after {j['attempts']} attempt(s){extra}")
    print("\n".join(lines))
    return 0


def cmd_analyse(a):
    from vfxlib.footage import analyse
    res = analyse(a.src, a.pattern, a.every)
    if "error" in res:
        return out(res, 2)
    if a.state:
        from vfxlib import state as st
        rp = os.path.join(st.paths(a.state)["dir"], f"{a.name}.json")
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        with open(rp, "w") as f:
            json.dump(res, f)
        try:
            st.record(a.state, a.name, [a.src, rp], params={"every": a.every, "pattern": a.pattern})
            st.set_values(a.state, [("facts.camera_move", f"{res['motion']} ({res['confidence']})")])
            res["recorded"] = a.name
        except st.StateError as e:
            res["state_error"] = str(e)
    return out(res, 0 if res["motion"] != "unknown" else 1)


def cmd_verify(a):
    if os.path.isfile(a.target) and os.path.splitext(a.target)[1].lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".mxf"):
        from vfxlib.video import verify_video
        res = verify_video(a.target, a.fps, a.seconds, not a.no_pixels)
    else:
        from vfxlib.frames import verify_sequence
        res = verify_sequence(a.target, a.start, a.end, a.since, not a.no_pixels)
    return out(res, 0 if res["status"] == "ok" else 1)


def _jobdirs(a):
    from vfxlib import state as st
    jd = st.paths(a.state)["jobs"] if a.state else os.path.join(a.logs, "jobs")
    return jd, a.logs


def cmd_run(a):
    from vfxlib import jobs
    jd, ld = _jobdirs(a)
    res = jobs.run(a.job, jd, ld, a.blend, a.script, a.blender, a.timeout, a.frames, a.pattern, a.output,
                   a.expect, a.expect_count, a.args, not a.no_pixels)
    return out(res, 0 if res["status"] == "success" else 1)


def cmd_resume(a):
    from vfxlib import jobs
    jd, ld = _jobdirs(a)
    res = jobs.resume(a.job, jd, ld, a.force)
    return out(res, 0 if res["status"] == "success" else 1)


def cmd_job(a):
    from vfxlib import jobs
    jd, _ = _jobdirs(a)
    res = jobs.status(jd, a.job)
    return out(res, 0 if res["status"] == "success" else 1)


def cmd_assets(a):
    from vfxlib import assets, hardware
    if a.op == "search":
        if a.vram or a.ram:
            budget = hardware.budget_for(ram=a.ram, vram=a.vram, unified=a.unified)
        else:
            m = hardware.detect()
            budget = {k: m[k] for k in ("tier", "render_memory_gb", "texture_res", "poly_ok", "poly_heavy")}
        res = assets.search(a.query, a.type, budget, a.limit)
        if a.sheet and res["options"]:
            res["sheet"] = assets.contact_sheet(res["options"], a.sheet) or "skipped (OpenCV not installed)"
        return out(res, 0 if res["options"] else 1)
    res = assets.download(a.source, a.query, a.type, a.res, a.dest, a.approved, a.licence_log)
    return out(res, 0 if res["status"] == "ok" else 1)


def cmd_tidy(a):
    from vfxlib.tidy import audit
    return out(audit(a.root, a.plan, a.clear_tmp, a.delete_duplicates))


def cmd_package(a):
    skill = os.path.dirname(HERE)
    n = 0
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(skill):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache")]
            for f in files:
                if f.endswith((".pyc", ".DS_Store")):
                    continue
                p = os.path.join(root, f)
                z.write(p, os.path.join(os.path.basename(skill), os.path.relpath(p, skill)))
                n += 1
    return out({"ok": True, "zip": a.out, "files": n, "kb": round(os.path.getsize(a.out) / 1024)})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vfx.py", description="blender-vfx engine " + __version__)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor"); p.add_argument("--blender"); p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("status"); p.add_argument("dir"); p.set_defaults(fn=cmd_status)

    p = sub.add_parser("state")
    p.add_argument("op", choices=["init", "show", "set", "done", "reopen", "record", "check", "invalidate", "recover"])
    p.add_argument("dir"); p.add_argument("items", nargs="*")
    p.add_argument("--shot"); p.add_argument("--mode", default="filmmaker", choices=["filmmaker", "vfx-artist"])
    p.add_argument("--note", default=""); p.add_argument("--deps", nargs="*"); p.add_argument("--params")
    p.set_defaults(fn=cmd_state)

    p = sub.add_parser("analyse"); p.add_argument("src"); p.add_argument("--pattern", default="*.png")
    p.add_argument("--every", type=int, default=4); p.add_argument("--state"); p.add_argument("--name", default="footage")
    p.set_defaults(fn=cmd_analyse)

    p = sub.add_parser("verify"); p.add_argument("target"); p.add_argument("--start", type=int)
    p.add_argument("--end", type=int); p.add_argument("--since", type=float); p.add_argument("--fps", type=float)
    p.add_argument("--seconds", type=float); p.add_argument("--no-pixels", action="store_true")
    p.set_defaults(fn=cmd_verify)

    for name, fn in (("run", cmd_run), ("resume", cmd_resume), ("job", cmd_job)):
        p = sub.add_parser(name); p.add_argument("job"); p.add_argument("--state"); p.add_argument("--logs", default="logs")
        if name == "run":
            p.add_argument("--blend"); p.add_argument("--script"); p.add_argument("--blender")
            p.add_argument("--timeout", type=int, default=3600); p.add_argument("--frames"); p.add_argument("--pattern")
            p.add_argument("--output"); p.add_argument("--expect"); p.add_argument("--expect-count", type=int)
            p.add_argument("--no-pixels", action="store_true"); p.add_argument("args", nargs="*")
        if name == "resume":
            p.add_argument("--force", action="store_true")
        p.set_defaults(fn=fn)

    p = sub.add_parser("assets"); p.add_argument("op", choices=["search", "download"]); p.add_argument("query")
    p.add_argument("--type", default="model", choices=["model", "texture", "hdri"]); p.add_argument("--limit", type=int, default=5)
    p.add_argument("--sheet"); p.add_argument("--vram", type=float); p.add_argument("--ram", type=float)
    p.add_argument("--unified", action="store_true"); p.add_argument("--source", default="polyhaven", choices=["polyhaven", "ambientcg"])
    p.add_argument("--res", default="2k"); p.add_argument("--dest", default="04_assets"); p.add_argument("--approved", action="store_true")
    p.add_argument("--licence-log"); p.set_defaults(fn=cmd_assets)

    p = sub.add_parser("tidy"); p.add_argument("root"); p.add_argument("--plan", action="store_true")
    p.add_argument("--clear-tmp", action="store_true"); p.add_argument("--delete-duplicates", action="store_true")
    p.set_defaults(fn=cmd_tidy)

    p = sub.add_parser("package"); p.add_argument("out"); p.set_defaults(fn=cmd_package)

    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "run" and "--" in argv:  # args after -- go to the Blender script
        i = argv.index("--")
        a = ap.parse_args(argv[:i])
        a.args = argv[i + 1:]
    else:
        a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
