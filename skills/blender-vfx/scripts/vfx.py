#!/usr/bin/env python3
"""blender-vfx engine. One command, compact JSON out. Plain Python 3.9+.

  vfx.py doctor                                  install and machine check
  vfx.py preflight [--root PROJECTS] [--shot SHOT_DIR] [--require-native]   PASS/FAIL per item, report per machine
  vfx.py event note|show|reconcile|scan SHOT_DIR ["text"]    the shot's event log
  vfx.py snapshot SHOT_DIR SCRIPT [--label NAME] record a script before running it
  vfx.py studio --root PROJECTS [--open]         local read-only viewer (127.0.0.1)
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
    from vfxlib import hardware
    from vfxlib.preflight import machine_facts
    f = machine_facts(a.blender)
    return out({"ok": not f["problems"], "engine": __version__, "python": platform.python_version(),
                "platform": sys.platform, "modules": f["mods"], "tools": f["tools"], "blender": f["blender"],
                "blender_path": f["blender_path"], "machine": hardware.detect(), "problems": f["problems"],
                "notes": f["notes"]}, 0 if not f["problems"] else 2)


def cmd_preflight(a):
    from vfxlib import preflight
    rep = preflight.run(a.blender, a.root, a.shot, a.require_native)
    path = None if a.no_report else preflight.write_report(rep, a.root, a.report)
    if path:
        rep["report"] = path
    if a.human:
        print(f"preflight on {rep['machine']}: {'READY' if rep['ok'] else 'NOT READY'} (engine {rep['engine']} {rep['commit'] or ''})")
        for i in rep["items"]:
            d = i["detail"] if isinstance(i["detail"], str) else json.dumps(i["detail"], default=str)
            print(f"  {i['status']:<15} {i['item']:<19} {d[:150]}")
        if path:
            print(f"report: {path}")
        return 0 if rep["ok"] else 1
    return out(rep, 0 if rep["ok"] else 1)


def cmd_event(a):
    from vfxlib import events as ev
    if a.op == "note":
        if not a.text:
            return out({"ok": False, "error": "event note needs text"}, 2)
        if a.status and a.status not in ev.STATUSES:
            return out({"ok": False, "error": f"status must be one of {ev.STATUSES}"}, 2)
        e = ev.append(a.dir, "note", source=a.source, summary=" ".join(a.text), status=a.status,
                      title=a.title, purpose=a.purpose, component=a.component)
        return out({"ok": True, "id": e["id"]})
    if a.op == "reconcile":
        return out({"ok": True, "interrupted": ev.reconcile(a.dir)})
    evs, _, bad = ev.read(a.dir, include_old=True)
    if a.op == "scan":
        r = ev.scan(a.dir, evs)
        return out({"ok": True, "unrecorded": r["count"], "files": r["files"][:20], "scanned": r["scanned"],
                    "truncated": r["truncated"]}, 0 if not r["count"] else 1)
    ops = ev.derive(evs)
    lines = []
    for o in ops[-a.last:]:
        lines.append(f"{o['op']}: {o['state']}" + (f" in {o['dur']} s" if o.get("dur") is not None else "")
                     + f" on {o.get('machine')}" + (f" ({'; '.join(map(str, o['errors']))[:120]})" if o.get("errors") else ""))
    notes = [e for e in evs if e.get("kind") == "note"][-3:]
    lines += [f"note ({e.get('source') or '?'}): {e.get('summary', '')}" for e in notes]
    if bad:
        lines.append(f"{bad} bad log line(s) ignored")
    print("\n".join(lines) or "no events")
    return 0


def cmd_snapshot(a):
    from vfxlib import events as ev
    if not os.path.isfile(a.file):
        return out({"ok": False, "error": f"not a file: {a.file}"}, 2)
    e = ev.snapshot(a.dir, a.file, a.label)
    if a.title or a.purpose or a.component:
        ev.append(a.dir, "note", source="snapshot", summary=f"About {e['label']}", title=a.title, purpose=a.purpose,
                  component=a.component, ref=e["id"])
    return out({"ok": True, "sha": e["sha"], "stored": e.get("stored"), "added": e.get("added"), "removed": e.get("removed")})


def cmd_studio(a):
    from vfxlib import studio
    if a.selftest:
        rep = studio.selftest(a.idle_seconds, report=a.report)
        if a.report:
            rep["report"] = a.report
        return out(rep, 0 if rep["ok"] else 1)
    if not a.root:
        return out({"ok": False, "error": "studio needs --root PROJECTS_FOLDER"}, 2)
    return studio.serve(a.root, a.port, a.open, a.telemetry_seconds)


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
    ap.add_argument("--title", help="short plain-language title for this step, shown in the Studio")
    ap.add_argument("--purpose", help="why this step is being done (the agent's own words)")
    ap.add_argument("--component", help="what it affects, e.g. 'Iris glass material' or 'compositor'")
    sub = ap.add_subparsers(dest="cmd", required=True)
    desc = argparse.ArgumentParser(add_help=False)  # the same three flags also work after the command
    for f in ("--title", "--purpose", "--component"):
        desc.add_argument(f, default=argparse.SUPPRESS)
    _add = sub.add_parser
    sub.add_parser = lambda *x, **k: _add(*x, parents=[desc], **k)

    p = sub.add_parser("doctor"); p.add_argument("--blender"); p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("preflight"); p.add_argument("--blender"); p.add_argument("--root"); p.add_argument("--shot")
    p.add_argument("--require-native", action="store_true"); p.add_argument("--report"); p.add_argument("--no-report", action="store_true")
    p.add_argument("--human", action="store_true"); p.set_defaults(fn=cmd_preflight)
    p = sub.add_parser("event"); p.add_argument("op", choices=["note", "show", "reconcile", "scan"]); p.add_argument("dir")
    p.add_argument("text", nargs="*"); p.add_argument("--source", default="agent"); p.add_argument("--status")
    p.add_argument("--last", type=int, default=15); p.set_defaults(fn=cmd_event)
    p = sub.add_parser("snapshot"); p.add_argument("dir"); p.add_argument("file"); p.add_argument("--label")
    p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("studio"); p.add_argument("--root"); p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true"); p.add_argument("--selftest", action="store_true")
    p.add_argument("--idle-seconds", type=float, default=60); p.add_argument("--report")
    p.add_argument("--telemetry-seconds", type=float, default=10.0, help="machine readings interval; 0 turns them off")
    p.set_defaults(fn=cmd_studio)
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

    p = sub.add_parser("verify"); p.add_argument("target"); p.add_argument("--state"); p.add_argument("--start", type=int)
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
    p.add_argument("--licence-log"); p.add_argument("--state"); p.set_defaults(fn=cmd_assets)

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
    shot = _event_shot(a)
    if not shot:
        return a.fn(a)
    return _logged(a, shot, argv)


def _event_shot(a):
    """Shot folder whose event log records this command, or None (read-only commands are not logged)."""
    if a.cmd == "state":
        return None if a.op in ("show", "check") else a.dir
    if a.cmd in ("analyse", "verify", "run", "resume") or (a.cmd == "assets" and a.op == "download"):
        return getattr(a, "state", None)
    if a.cmd == "tidy" and os.path.isdir(os.path.join(a.root, "state")):
        return a.root
    return None


def _logged(a, shot, argv):
    import signal
    from vfxlib import common, events as ev
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # still write the end event on a polite kill
    name = a.cmd + (f" {a.op}" if hasattr(a, "op") else "")
    args = [ev.rel(shot, x) if os.path.isabs(x) else x for x in argv]
    with ev.Op(shot, name, args=args, timeout=getattr(a, "timeout", None), title=a.title, purpose=a.purpose,
               component=a.component) as o:
        common.out.last = None
        code = a.fn(a)
        res = common.out.last if isinstance(common.out.last, dict) else {}
        st = str(res.get("status", "")).lower()
        if a.cmd == "analyse" and res.get("motion") == "unknown":
            o.status = "UNKNOWN"
        elif st in ("success", "ok") or (not st and code == 0):
            o.status = "PASS"
        else:
            o.status = "FAIL"
        errs = res.get("errors") or ([res["error"]] if res.get("error") else None)
        o.errors = errs
        o.summary = {k: res[k] for k in ("status", "motion", "confidence", "frames", "missing", "rerender",
                                         "forgotten", "next", "stage", "attempts") if k in res} or None
        outs = [getattr(a, k, None) for k in ("pattern", "output", "sheet", "dest")]
        outs += [res.get(k) for k in ("zip", "sheet", "path")]
        o.outputs = [ev.rel(shot, x) for x in outs if isinstance(x, str) and x] or None
    return code


if __name__ == "__main__":
    sys.exit(main())
