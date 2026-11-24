import json
import os
import sys

from conftest import ROOT
from vfxlib import jobs
from vfxlib.common import FileLock

FAKE = os.path.join(ROOT, "tests", "fake_blender.py")


def _run(tmp_path, job, frames="1-10", timeout=60, env=None):
    os.environ.update(env or {})
    out = str(tmp_path / "renders" / "####")
    try:
        return jobs.run(job, str(tmp_path / "jobs"), str(tmp_path / "logs"), blend=None, script=None,
                        blender=f"{sys.executable}|{FAKE}", timeout=timeout, frames=frames,
                        pattern=str(tmp_path / "renders" / "####.png"), output=out)
    finally:
        for k in (env or {}):
            os.environ.pop(k, None)


def test_success(tmp_path):
    r = _run(tmp_path, "ok")
    assert r["status"] == "success", r
    assert r["check"]["found"] == 10 and "seconds_per_frame" in r


def test_crash_then_resume_only_missing(tmp_path):
    log = str(tmp_path / "frames.log")
    r = _run(tmp_path, "crash", env={"FAKE_CRASH_AT": "6", "FAKE_LOG": log})
    assert r["status"] == "incomplete" and r["check"]["rerender"] == "6-10"
    assert any("crashed" in e or "exited" in e for e in r["errors"])
    open(log, "w").close()
    os.environ["FAKE_LOG"] = log
    try:
        r2 = jobs.resume("crash", str(tmp_path / "jobs"), str(tmp_path / "logs"))
    finally:
        os.environ.pop("FAKE_LOG")
    assert r2["status"] == "success", r2
    assert open(log).read().split() == ["6", "7", "8", "9", "10"]
    assert r2["attempt"] == 2


def test_timeout(tmp_path):
    r = _run(tmp_path, "slow", frames="1-20", timeout=1, env={"FAKE_SLEEP": "0.3"})
    assert r["status"] in ("incomplete", "failed") and "timed out" in r["errors"][0]


def test_black_frame_fails_but_is_not_rerendered(tmp_path):
    import pytest
    pytest.importorskip("cv2")
    r = _run(tmp_path, "black", env={"FAKE_BLACK": "5"})
    assert r["status"] != "success" and r["check"]["black"] == "5"
    r2 = jobs.resume("black", str(tmp_path / "jobs"), str(tmp_path / "logs"))
    assert "fix the scene" in r2["errors"][0]


def test_interrupted_job_detected_and_resumed(tmp_path):
    r = _run(tmp_path, "cut", env={"FAKE_CRASH_AT": "4"})
    m = json.load(open(tmp_path / "jobs" / "cut.json"))
    m["status"], m["pid"] = "running", 999999  # as if the session died mid-render
    json.dump(m, open(tmp_path / "jobs" / "cut.json", "w"))
    s = jobs.status(str(tmp_path / "jobs"), "cut")
    assert s["status"] == "interrupted" and s["check"]["rerender"] == "4-10"
    assert jobs.resume("cut", str(tmp_path / "jobs"), str(tmp_path / "logs"))["status"] == "success"


def test_attempt_limit_and_duplicate_ids(tmp_path):
    _run(tmp_path, "lim", env={"FAKE_CRASH_AT": "2"})
    for _ in range(2):
        os.environ["FAKE_CRASH_AT"] = "2"
        jobs.resume("lim", str(tmp_path / "jobs"), str(tmp_path / "logs"))
    os.environ.pop("FAKE_CRASH_AT")
    r = jobs.resume("lim", str(tmp_path / "jobs"), str(tmp_path / "logs"))
    assert "stop and ask" in r["errors"][0]
    assert jobs.resume("lim", str(tmp_path / "jobs"), str(tmp_path / "logs"), force=True)["status"] == "success"
    assert _run(tmp_path, "lim")["status"] == "exists"


def test_two_jobs_cannot_write_same_folder(tmp_path):
    os.makedirs(tmp_path / "renders", exist_ok=True)
    with FileLock(str(tmp_path / "renders" / ".render.lock")):
        assert _run(tmp_path, "blocked")["status"] == "blocked"
