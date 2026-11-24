"""Run a headless Blender job and prove it worked.

Usage:
  python3 run_job.py --job shot010_render_v004 --blend 05_blend/SHOT010/SHOT010_v004.blend \
      --script scripts/04_render.py --timeout 7200 \
      --expect "07_renders/SHOT010/v004/beauty/*.exr" --expect-count 108 -- --frames 1-108

Runs `blender -b <blend> -P <script> -- <args>` (or just the script with -b if no
blend), with a timeout, a log file in logs/<job>.log, and then checks the
outputs really exist: count, non-empty, newer than the job start.
Prints one JSON result. A tool or MCP saying "success" is never enough;
this result is what the agent reports.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time


def find_blender(given):
    if given:
        return given
    for c in ("blender", "/Applications/Blender.app/Contents/MacOS/Blender",
              r"C:\Program Files\Blender Foundation\Blender\blender.exe"):
        if shutil.which(c) or os.path.exists(c):
            return c
    return None


def main():
    argv = sys.argv[1:]
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--blend")
    ap.add_argument("--script", required=True)
    ap.add_argument("--blender")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--expect", help="glob of files the job must produce")
    ap.add_argument("--expect-count", type=int)
    ap.add_argument("--logs", default="logs")
    a = ap.parse_args(argv)

    blender = find_blender(a.blender)
    result = {"job_id": a.job, "status": "failed", "errors": [], "warnings": []}
    if not blender:
        result["errors"].append("Blender executable not found; pass --blender")
        print(json.dumps(result)); return 2

    cmd = [blender, "-b"] + ([a.blend] if a.blend else []) + ["-P", a.script, "--"] + extra
    os.makedirs(a.logs, exist_ok=True)
    log_path = os.path.join(a.logs, f"{a.job}.log")
    start = time.time()
    try:
        with open(log_path, "w") as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout)
        result["exit_code"] = proc.returncode
    except subprocess.TimeoutExpired:
        result["errors"].append(f"timed out after {a.timeout} s")
        result["exit_code"] = None
    result["seconds"] = round(time.time() - start, 1)
    result["log"] = log_path

    try:
        with open(log_path, errors="replace") as fh:
            tail = fh.readlines()[-200:]
        errs = [l.strip() for l in tail if "Error" in l or "Traceback" in l or "EXCEPTION" in l]
        if errs:
            result["errors"].extend(errs[-5:])
    except OSError:
        pass

    if a.expect:
        files = [f for f in glob.glob(a.expect) if os.path.isfile(f)]
        fresh = [f for f in files if os.path.getmtime(f) >= start - 1]
        empty = [f for f in fresh if os.path.getsize(f) == 0]
        result["files_found"] = len(files)
        result["files_new"] = len(fresh)
        if empty:
            result["errors"].append(f"{len(empty)} empty output files")
        if a.expect_count is not None:
            result["files_expected"] = a.expect_count
            if len(fresh) != a.expect_count:
                result["errors"].append(f"expected {a.expect_count} new files, found {len(fresh)}")
        elif not fresh:
            result["errors"].append("no new output files")
        if len(files) > len(fresh):
            result["warnings"].append(f"{len(files) - len(fresh)} older files matched; they were not written by this job")

    if result.get("exit_code") == 0 and not result["errors"]:
        result["status"] = "success"
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
