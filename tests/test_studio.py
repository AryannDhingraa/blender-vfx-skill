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
