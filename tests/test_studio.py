import json
import os
import sys

import pytest

from vfxlib import events as ev
from vfxlib import state as st
from vfxlib import studio


def test_selftest_passes_with_short_idle():
    rep = studio.selftest(idle_seconds=3, n_events=10)
    failed = {k: v for k, v in rep["results"].items() if v["status"] != "PASS"}
    if sys.platform == "win32":  # symlinks need admin on Windows; CPU sampling is coarse there
        failed.pop("idle_cpu_under_1pct", None)
    assert not failed, failed


def test_safe_path(tmp_path):
    base = tmp_path / "shot"
    (base / "_review").mkdir(parents=True)
    (base / "_review" / "a.png").write_bytes(b"x")
    (base / ".hidden.png").write_bytes(b"x")
    ok = studio.safe_path(str(base), "_review/a.png", studio.IMAGE_TYPES)
    assert ok and ok.endswith("a.png")
    for bad in ["../x.png", "/etc/passwd", "_review/../_review/a.png", ".hidden.png", "_review//a.png",
                "_review\\a.png", "C:/x.png", "_review/a.png\x00.png", "_review/my_token.png", "_review/a.txt"]:
        assert studio.safe_path(str(base), bad, studio.IMAGE_TYPES) is None, bad
    if sys.platform != "win32":
        os.symlink(str(tmp_path), str(base / "_review" / "up"))
        assert studio.safe_path(str(base), "_review/up/shot/_review/a.png", studio.IMAGE_TYPES) is None


def test_discovery_skips_engine_and_symlinks(tmp_path):
    root = tmp_path / "root"
    st.init(str(root / "benchmarks" / "iris"), "iris")
    st.init(str(root / "_studio" / "engine" / "fake"), "fake")
    ev.append(str(root / "alien"), "note", summary="x")
    if sys.platform != "win32":
        os.symlink(str(root / "benchmarks"), str(root / "linked"))
    hub = studio.Hub(str(root))
    hub.discover()
    assert sorted(hub.shots) == ["alien", "benchmarks/iris"]


def test_state_has_no_token_and_derives_ops(tmp_path):
    root = tmp_path / "root"
    shot = root / "s"
    with ev.Op(str(shot), "verify") as o:
        o.status = "FAIL"
    (root / "_studio" / "preflight").mkdir(parents=True)
    (root / "_studio" / "preflight" / "mac.json").write_text(json.dumps({"ok": True, "items": []}))
    (root / "_studio" / "preflight" / "evil.json").write_text("{}")
    srv = studio.start(str(root), 0, quiet=True)
    try:
        s = srv.hub.state()
        assert s["shots"][0]["ops"][0]["state"] == "FAIL"
        assert list(s["preflight"]) == ["mac"]
        assert srv.token not in json.dumps(s)
    finally:
        srv.hub.stop.set()
        srv.shutdown()


def test_plain_words_cover_logged_ops():
    from vfxlib import plain
    for op in ("state init", "state record", "analyse", "verify", "run", "resume", "assets download", "tidy", "preflight", "snapshot"):
        title, what, effect, manual = plain.describe(op)
        assert title and what and not title.startswith("Technical step")
    assert plain.describe("frobnicate")[0].startswith("Technical step")


def test_telemetry_reports_or_says_unavailable(tmp_path):
    from vfxlib.telemetry import Sampler
    s = Sampler(str(tmp_path))
    s.sample()
    t = s.sample()
    for k in ("cpu", "gpu", "memory", "pressure", "swap", "disk", "thermal", "workloads", "studio"):
        assert k in t and isinstance(t[k], dict) and ("available" in t[k])
        if not t[k]["available"]:
            assert t[k]["why"]
    assert t["disk"]["available"] and t["sample_cpu_s"] < 1.0
    if sys.platform == "darwin":  # real readings on macOS (CI runners and the user's Mac)
        for k in ("cpu", "memory", "pressure", "swap", "thermal"):
            assert t[k]["available"], (k, t[k])
        m = t["memory"]
        assert 1 < m["total_gb"] < 4096 and 0 < m["used_pct"] <= 100 and m["unified"] is True, m
        assert 0 <= t["cpu"]["busy_pct"] <= 100 and t["pressure"]["level"] in ("normal", "warning", "critical"), t
        assert t["swap"]["used_gb"] <= t["swap"]["total_gb"] + 0.01 and t["thermal"]["state"] in ("nominal", "fair", "serious", "critical")
        costs = [s.sample()["sample_cpu_s"] for _ in range(6)]  # fast samples plus two slow ones
        assert sum(costs) / len(costs) < 0.03, costs  # under 0.3% at one sample every 10 s
    if sys.platform == "win32":
        assert t["cpu"]["available"] and t["memory"]["available"], t
    if sys.platform.startswith("linux"):
        assert t["cpu"]["available"] and t["memory"]["available"]


def test_alerts_dedupe_and_resolve():
    a = studio.Alerts(started=0)
    ops = [{"op": "verify", "op_id": "1", "state": "FAIL", "t": 10, "errors": ["missing frames 3-4"]}]
    tel = {"disk": {"available": True, "free_pct": 4.0, "free_gb": 12, "path": "/x"}, "pressure": {"available": True, "level": "normal"}}
    for now in (100, 105, 110):
        a.update([("s", ops)], tel, now, "/")
    act = a.list()["active"]
    assert len(act) == 2 and {x["key"] for x in act} == {"op:s:1", "disk-low"} and all(x["count"] == 1 for x in act)
    ops.append({"op": "verify", "op_id": "2", "state": "PASS", "t": 20})
    tel["disk"]["free_pct"], tel["disk"]["free_gb"] = 40.0, 400
    a.update([("s", ops)], tel, 120, "/")
    assert a.list()["active"] == [] and len(a.list()["recent"]) == 2
    tel["pressure"]["level"] = "warning"
    a.update([("s", ops)], tel, 130, "/")
    assert not a.list()["active"]  # pressure must last 60 s before it alerts
    a.update([("s", ops)], tel, 195, "/")
    assert a.list()["active"][0]["key"] == "memory-pressure"
