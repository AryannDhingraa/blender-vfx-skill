import json
import multiprocessing
import os
import time

import pytest

from vfxlib import state as st
from vfxlib.common import FileLock, LockTimeout, compress_ranges, parse_ranges, blender_frames


def test_ranges():
    assert compress_ranges([5, 1, 2, 3, 7, 9, 10]) == "1-3,5,7,9-10"
    assert parse_ranges("1-3,7,9..10") == [1, 2, 3, 7, 9, 10]
    assert blender_frames([1, 2, 3, 7]) == "1..3,7"
    assert compress_ranges([]) == ""


def test_init_set_done_reopen(tmp_path):
    d = str(tmp_path)
    st.init(d, "sh010")
    with pytest.raises(st.StateError):
        st.init(d, "sh010")
    st.set_values(d, [("facts.fps", 25), ("mode", "vfx-artist")])
    s = st.done(d, "brief")
    s = st.done(d, "plate")
    assert s["stage"] == "analyse" and s["mode"] == "vfx-artist"
    s = st.done(d, "analyse")
    s = st.reopen(d, "plate")
    assert s["done"] == ["brief"] and s["stage"] == "plate"


def test_validation_refuses_bad_values(tmp_path):
    d = str(tmp_path)
    st.init(d, "x")
    for bad in [("mode", "wizard"), ("budget", "lots"), ("learning", "yes"), ("seq", 3)]:
        with pytest.raises(st.StateError):
            st.set_values(d, [bad])
    assert st.load(d)[0]["mode"] == "filmmaker"


def test_size_cap(tmp_path):
    d = str(tmp_path)
    st.init(d, "x")
    with pytest.raises(st.StateError):
        st.set_values(d, [("facts.big", "a" * 5000)])


def test_dependency_invalidation(tmp_path):
    d = str(tmp_path)
    st.init(d, "x")
    plate = tmp_path / "plate.mp4"
    plate.write_bytes(b"one")
    solve = tmp_path / "solve.json"
    solve.write_text("{}")
    rend = tmp_path / "renders"
    rend.mkdir()
    (rend / "0001.png").write_bytes(b"x")
    st.record(d, "plate", [str(plate)])
    st.record(d, "solve", [str(solve)], deps=["plate"], params={"focal": 16})
    st.record(d, "render", [str(rend)], deps=["solve"])
    s = st.load(d)[0]
    assert st.stale(d, s) == {}
    assert st.check(d, s, "solve", {"focal": 16})["valid"]
    assert "settings changed" in st.check(d, s, "solve", {"focal": 18})["reasons"]
    # changing the plate makes everything downstream stale, without deleting it
    plate.write_bytes(b"two")
    bad = st.stale(d, st.load(d)[0])
    assert set(bad) == {"plate", "solve", "render"}
    assert "input plate is stale" in bad["solve"]
    # re-recording the plate marks the solve as built from an old input
    st.record(d, "plate", [str(plate)])
    bad = st.stale(d, st.load(d)[0])
    assert "input plate was redone" in bad["solve"] and "render" in bad and "plate" not in bad
    # a new frame in a render folder is noticed
    st.record(d, "solve", [str(solve)], deps=["plate"])
    st.record(d, "render", [str(rend)], deps=["solve"])
    (rend / "0002.png").write_bytes(b"y")
    assert "render" in st.stale(d, st.load(d)[0])
    _, gone = st.invalidate(d, "solve")
    assert gone == ["render", "solve"]
    assert list(st.load(d)[0]["results"]) == ["plate"]


def test_cycles_and_missing_deps_refused(tmp_path):
    d = str(tmp_path)
    st.init(d, "x")
    f = tmp_path / "a"
    f.write_text("1")
    with pytest.raises(st.StateError):
        st.record(d, "b", [str(f)], deps=["nope"])
    with pytest.raises(st.StateError):
        st.record(d, "b", [str(tmp_path / "missing")])
    st.record(d, "a", [str(f)])
    st.record(d, "b", [str(f)], deps=["a"])
    with pytest.raises(st.StateError):
        st.record(d, "a", [str(f)], deps=["b"])


def test_recovery_from_corruption(tmp_path):
    d = str(tmp_path)
    st.init(d, "x")
    st.done(d, "brief")
    st.done(d, "plate")
    p = st.paths(d)
    with open(p["cur"], "w") as f:
        f.write("{broken")
    s, src, problems = st.load(d)
    assert src == "history" and s["done"] == ["brief", "plate"] and problems
    # a torn last history line is skipped, the one before it is used
    with open(p["hist"], "a") as f:
        f.write('{"seq": 99, "state": {"half')
    s, src, _ = st.load(d)
    assert s["done"] == ["brief", "plate"]
    # checksum mismatch is skipped too
    lines = open(p["hist"]).read().splitlines()
    e = json.loads(lines[-2])
    e["state"]["done"] = ["brief", "plate", "analyse"]
    with open(p["hist"], "a") as f:
        f.write("\n" + json.dumps(e) + "\n")
    s, src, _ = st.load(d)
    assert s["done"] == ["brief", "plate"]
    # any write repairs the file
    st.set_values(d, [("facts.k", 1)])
    assert st.load(d)[1] == "current"
    # history gone and state gone: backup still works
    os.remove(p["hist"])
    with open(p["cur"], "w") as f:
        f.write("")
    s, src, _ = st.load(d)
    assert src == "backup" and s["done"] == ["brief", "plate"]


def _hold(path, secs):
    with FileLock(path):
        time.sleep(secs)


def test_lock_blocks_and_releases_on_crash(tmp_path):
    lock = str(tmp_path / ".lock")
    p = multiprocessing.Process(target=_hold, args=(lock, 3))
    p.start()
    time.sleep(0.8)
    with pytest.raises(LockTimeout):
        with FileLock(lock, timeout=0.3):
            pass
    p.terminate()  # a crashed holder must not leave a stale lock
    p.join()
    with FileLock(lock, timeout=1):
        pass


def _writer(d, n):
    for i in range(n):
        st.set_values(d, [(f"facts.w{os.getpid()}_{i}", i)])


def test_concurrent_writers_lose_nothing(tmp_path):
    d = str(tmp_path)
    st.init(d, "x")
    procs = [multiprocessing.Process(target=_writer, args=(d, 8)) for _ in range(3)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    s = st.load(d)[0]
    assert len(s["facts"]) == 24 and s["seq"] == 25


def test_summary_is_short(tmp_path):
    d = str(tmp_path)
    st.init(d, "sh010")
    f = tmp_path / "plate.mp4"
    f.write_text("x")
    st.record(d, "plate", [str(f)])
    f.write_text("y")
    text = st.summary(d)
    assert "plate (STALE: plate.mp4 changed)" in text and len(text.splitlines()) <= 6
