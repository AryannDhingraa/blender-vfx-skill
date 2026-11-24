"""Headless Blender jobs with proof: timeout, log, verified outputs, and
resume that re-renders only missing, corrupt or stale frames.

A manifest per job (<shot>/state/jobs/<id>.json, or logs/jobs/) records the
command, frames, output pattern, attempts and result, so a job cut off by a
crash, a closed laptop or a lost session can be checked and resumed later.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

from .common import FileLock, LockTimeout, atomic_write, blender_frames, parse_ranges, pid_alive
from .frames import verify_sequence

ERROR_MARKS = ("Error:", "Traceback", "EXCEPTION", "Segmentation fault", "out of memory",
               "Out of memory", "CUDA error", "Killed", "Fatal")
MAX_ATTEMPTS = 3


def find_blender(given=None):
    if given:
        return given
    env = os.environ.get("BLENDER")
    if env:
        return env
    cands = ["blender"]
    if sys.platform == "darwin":
        cands.append("/Applications/Blender.app/Contents/MacOS/Blender")
    elif sys.platform == "win32":
        cands += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    for c in cands:
        if shutil.which(c) or os.path.isfile(c):
            return shutil.which(c) or c
    return None


def _mpath(jobs_dir, job):
    return os.path.join(jobs_dir, f"{job}.json")


def load_manifest(jobs_dir, job):
    try:
        with open(_mpath(jobs_dir, job), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save(jobs_dir, m):
    os.makedirs(jobs_dir, exist_ok=True)
    atomic_write(_mpath(jobs_dir, m["job"]), json.dumps(m, indent=1))


def _log_errors(log_path):
    try:
        with open(log_path, errors="replace") as fh:
            tail = fh.readlines()[-300:]
    except OSError:
        return []
    return [l.strip()[:200] for l in tail if any(k in l for k in ERROR_MARKS)][-5:]


def _cmd(m, frames):
    base = m["blender"] if isinstance(m["blender"], list) else [m["blender"]]
    cmd = base + ["-b"] + ([m["blend"]] if m.get("blend") else []) + ["--python-exit-code", "1"]
    if m.get("script"):
        cmd += ["-P", m["script"]]
    if m.get("output"):
        cmd += ["-o", m["output"]]
    if frames:
        cmd += ["-f", blender_frames(frames)]
    return cmd + ["--"] + list(m.get("args", []))


def _verify(m, since):
    if m.get("pattern"):
        fr = parse_ranges(m["frames"])
        return verify_sequence(m["pattern"], min(fr), max(fr), since=since, pixels=m.get("pixels", True))
    if m.get("expect"):
        files = [f for f in glob.glob(m["expect"]) if os.path.isfile(f)]
        fresh = [f for f in files if os.path.getmtime(f) >= since - 1]
        res = {"type": "files", "found": len(files), "new": len(fresh),
               "empty": sum(1 for f in fresh if os.path.getsize(f) == 0), "rerender": ""}
        want = m.get("expect_count")
        ok = fresh and not res["empty"] and (want is None or len(fresh) == want)
        res["status"] = "ok" if ok else "failed"
        if want is not None:
            res["expected"] = want
        return res
    return {"type": "none", "status": "ok", "rerender": "", "note": "no outputs declared; only exit code checked"}


def _execute(m, frames, jobs_dir, logs_dir, since):
    lock_dir = os.path.dirname(m["pattern"]) if m.get("pattern") else (logs_dir or ".")
    os.makedirs(lock_dir or ".", exist_ok=True)
    try:
        with FileLock(os.path.join(lock_dir or ".", ".render.lock"), timeout=0):
            os.makedirs(logs_dir, exist_ok=True)
            log_path = os.path.join(logs_dir, f"{m['job']}.log")
            m["attempts"].append({"started": time.time(), "frames": m["frames"] if frames is None else
                                  ",".join(map(str, frames)) if len(frames) < 40 else f"{len(frames)} frames"})
            m["status"], m["log"] = "running", log_path
            t0 = time.time()
            with open(log_path, "w") as log:
                proc = subprocess.Popen(_cmd(m, frames), stdout=log, stderr=subprocess.STDOUT)
                m["pid"] = proc.pid
                _save(jobs_dir, m)
                try:
                    code = proc.wait(timeout=m["timeout"])
                    timed_out = False
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    code, timed_out = None, True
    except LockTimeout:
        return {"job": m["job"], "status": "blocked", "errors": ["another job is writing to the same output folder"]}
    att = m["attempts"][-1]
    att.update({"exit_code": code, "seconds": round(time.time() - t0, 1), "timed_out": timed_out})
    errors = _log_errors(log_path)
    if timed_out:
        errors.insert(0, f"timed out after {m['timeout']} s")
    elif code not in (0, None):
        errors.insert(0, f"Blender exited with code {code}")
    check = _verify(m, since)
    if check["status"] != "ok" and not errors:
        errors.append("outputs failed verification")
    m["status"] = "success" if code == 0 and check["status"] == "ok" and not timed_out else \
        ("incomplete" if check.get("rerender") else "failed")
    m["pid"] = None
    m["last_check"] = {k: v for k, v in check.items() if v not in ("", {}, 0) or k in ("status", "found")}
    m["errors"] = errors
    _save(jobs_dir, m)
    n = len(parse_ranges(m["frames"])) if m.get("frames") else None
    res = {"job": m["job"], "status": m["status"], "attempt": len(m["attempts"]), "seconds": att["seconds"],
           "errors": errors, "check": m["last_check"], "log": log_path}
    if n and frames:
        res["seconds_per_frame"] = round(att["seconds"] / max(1, len(frames)), 1)
    if m["status"] == "incomplete":
        res["next"] = f"resume re-renders frames {check['rerender']}"
    return res


def run(job, jobs_dir, logs_dir, blend=None, script=None, blender=None, timeout=3600, frames=None,
        pattern=None, output=None, expect=None, expect_count=None, args=(), pixels=True):
    exe = find_blender(blender)
    if not exe:
        return {"job": job, "status": "failed", "errors": ["Blender not found; pass --blender or set BLENDER"]}
    old = load_manifest(jobs_dir, job)
    if old and old.get("status") == "running" and pid_alive(old.get("pid")):
        return {"job": job, "status": "running", "errors": ["this job is already running"]}
    if old:
        return {"job": job, "status": "exists", "errors": ["job id already used; use resume or a new id"]}
    if pattern and not frames:
        return {"job": job, "status": "failed", "errors": ["--pattern needs --frames"]}
    m = {"job": job, "blender": exe.split("|") if "|" in exe else exe, "blend": blend, "script": script,
         "timeout": timeout, "frames": frames, "pattern": pattern, "output": output, "expect": expect,
         "expect_count": expect_count, "args": list(args), "pixels": pixels, "attempts": [], "created": time.time()}
    fr = parse_ranges(frames) if frames else None
    return _execute(m, fr, jobs_dir, logs_dir, since=m["created"])


def status(jobs_dir, job):
    m = load_manifest(jobs_dir, job)
    if m is None:
        return {"job": job, "status": "unknown", "errors": ["no manifest"]}
    if m["status"] == "running" and not pid_alive(m.get("pid")):
        m["status"] = "interrupted"
    out = {"job": job, "status": m["status"], "attempts": len(m["attempts"]), "errors": m.get("errors", [])}
    if m["status"] in ("interrupted", "incomplete", "failed"):
        chk = _verify(m, m["created"])
        out["check"] = {k: v for k, v in chk.items() if v not in ("", {}, 0) or k == "status"}
    return out


def resume(job, jobs_dir, logs_dir, force=False):
    m = load_manifest(jobs_dir, job)
    if m is None:
        return {"job": job, "status": "unknown", "errors": ["no manifest"]}
    if m["status"] == "running" and pid_alive(m.get("pid")):
        return {"job": job, "status": "running", "errors": ["still running; wait for it"]}
    if m["status"] == "success":
        return {"job": job, "status": "success", "errors": [], "note": "nothing to resume"}
    if len(m["attempts"]) >= MAX_ATTEMPTS and not force:
        return {"job": job, "status": m["status"], "errors": [f"{len(m['attempts'])} attempts already; "
                "stop and ask the user before trying again (pass --force after they agree)"]}
    if not m.get("pattern"):
        return _execute(m, parse_ranges(m["frames"]) if m.get("frames") else None, jobs_dir, logs_dir, time.time())
    chk = _verify(m, m["created"])
    todo = parse_ranges(chk["rerender"]) if chk.get("rerender") else []
    if not todo:
        m["status"] = "success" if chk["status"] == "ok" else m["status"]
        _save(jobs_dir, m)
        return {"job": job, "status": m["status"], "errors": [] if chk["status"] == "ok" else
                ["frames are all present but pixel checks failed (black or flicker); fix the scene, not the job"],
                "check": chk}
    return _execute(m, todo, jobs_dir, logs_dir, since=m["created"])
