import json
import os
import subprocess
import sys
import time

import pytest

from conftest import SCRIPTS
from vfxlib import events as ev
from vfxlib import state as st

VFX = os.path.join(SCRIPTS, "vfx.py")


def run(*args):
    r = subprocess.run([sys.executable, VFX, *args], capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout


def test_append_read_and_checksum(tmp_path):
    shot = str(tmp_path / "s")
    for i in range(5):
        ev.append(shot, "note", summary=f"n{i}")
    evs, off, bad = ev.read(shot)
    assert [e["summary"] for e in evs] == [f"n{i}" for i in range(5)] and bad == 0
    with open(ev.paths(shot)["log"], "ab") as f:
        f.write(b'{"kind":"note","summary":"forged","crc":1}\n')  # bad crc
        f.write(b"not json\n")
        f.write(b'{"kind":"note","summary":"torn"')  # unterminated: still being written
    evs2, off2, bad2 = ev.read(shot, off)
    assert evs2 == [] and bad2 == 2
    evs3, _, _ = ev.read(shot, off2)
    assert evs3 == []  # torn line waits until it is complete


def test_lines_stay_compact(tmp_path):
    shot = str(tmp_path / "s")
    e = ev.append(shot, "op.end", op="x", op_id="a", args=["y" * 5000] * 50, errors=["z" * 9000], summary={"k": "v" * 9000})
    with open(ev.paths(shot)["log"], "rb") as f:
        line = f.read().splitlines()[-1]
    assert len(line) <= ev.MAX_LINE and e.get("clipped") is True
    assert ev.read(shot)[0][-1]["op"] == "x"


def test_rotation_keeps_one_generation(tmp_path, monkeypatch):
    shot = str(tmp_path / "s")
    monkeypatch.setattr(ev, "ROTATE_BYTES", 2000)
    for i in range(60):
        ev.append(shot, "note", summary=f"n{i}")
    assert os.path.exists(ev.paths(shot)["old"])
    evs, _, bad = ev.read(shot, include_old=True)
    assert bad == 0 and evs[-1]["summary"] == "n59"


def test_op_states(tmp_path):
    shot = str(tmp_path / "s")
    with ev.Op(shot, "ok-op") as o:
        o.status = "PASS"
    with pytest.raises(ValueError):
        with ev.Op(shot, "boom"):
            raise ValueError("bad")
    ops = {o["op"]: o for o in ev.derive(ev.read(shot)[0])}
    assert ops["ok-op"]["state"] == "PASS" and ops["boom"]["state"] == "FAIL" and "ValueError" in ops["boom"]["errors"][0]


def test_killed_process_is_interrupted_and_reconciled(tmp_path):
    shot = str(tmp_path / "s")
    code = ("import sys,os; sys.path.insert(0, %r)\nfrom vfxlib import events as ev\n"
            "ev.Op(%r, 'render').__enter__()\nos._exit(9)\n") % (SCRIPTS, shot)
    subprocess.run([sys.executable, "-c", code], timeout=60)
    ops = ev.derive(ev.read(shot)[0])
    assert ops[-1]["state"] == "interrupted"
    assert run("event", "reconcile", shot)[0] == 0
    evs = ev.read(shot)[0]
    assert evs[-1]["kind"] == "op.interrupted" and ev.derive(evs)[-1]["state"] == "interrupted"
    assert ev.reconcile(shot) == []  # only once


def test_running_reused_pid_and_remote(tmp_path):
    shot = str(tmp_path / "s")
    with ev.Op(shot, "live"):
        assert ev.derive(ev.read(shot)[0])[-1]["state"] == "running"
    t = time.time()
    evs = [{"kind": "op.start", "op_id": "r1", "op": "remote", "t": t - 10, "host": "other|darwin", "pid": 1, "timeout": 3600},
           {"kind": "op.start", "op_id": "r2", "op": "late", "t": t - 9000, "host": "other|darwin", "pid": 1, "timeout": 100},
           {"kind": "op.start", "op_id": "r3", "op": "reused", "t": t, "host": ev.host_id(), "pid": os.getpid(), "pid_start": "old"}]
    states = {o["op"]: o["state"] for o in ev.derive(evs)}
    reused = "running" if sys.platform == "win32" else "interrupted"  # no process start time on Windows
    assert states == {"remote": "unknown-remote", "late": "interrupted", "reused": reused}


def test_snapshot_dedup_and_diff(tmp_path):
    shot = str(tmp_path / "s")
    script = tmp_path / "comp.py"
    script.write_text("a = 1\nb = 2\n")
    e1 = ev.snapshot(shot, str(script), "comp")
    e1b = ev.snapshot(shot, str(script), "comp")
    assert e1["sha"] == e1b["sha"] and e1b["added"] == 0 and len(os.listdir(ev.paths(shot)["snaps"])) == 1
    script.write_text("a = 1\nb = 3\nc = 4\n")
    assert ev.load_snapshot(shot, e1["sha"]) == script.read_bytes().decode().replace("b = 3\r\nc = 4", "b = 2").replace("b = 3\nc = 4", "b = 2")
    e2 = ev.snapshot(shot, str(script), "comp")
    assert (e2["added"], e2["removed"]) == (2, 1)
    d = ev.diff(shot, e1["sha"], e2["sha"])
    assert "+b = 3" in d and "-b = 2" in d
    big = tmp_path / "big.py"
    big.write_text("x" * (ev.SNAP_MAX + 10))
    e3 = ev.snapshot(shot, str(big))
    assert e3["stored"] is False and not os.path.exists(os.path.join(ev.paths(shot)["snaps"], e3["sha"] + ".txt"))
    assert ev.load_snapshot(shot, "../../etc/passw") is None


def test_scan_separates_recorded_from_unrecorded(tmp_path):
    shot = str(tmp_path / "s")
    st.init(shot, "s")
    old = tmp_path / "s" / "plate.mov"
    old.write_text("old")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    ev.append(shot, "note", summary="start")
    time.sleep(2.2)
    (tmp_path / "s" / "renders").mkdir()
    (tmp_path / "s" / "renders" / "0001.exr").write_text("r")
    (tmp_path / "s" / "hand_edit.blend").write_text("b")
    ev.append(shot, "op.end", op="run", op_id="x", status="PASS", outputs=["renders"])
    r = ev.scan(shot, ev.read(shot)[0])
    assert [f["path"] for f in r["files"]] == ["hand_edit.blend"]


def test_cli_commands_write_one_start_and_end(tmp_path):
    shot = str(tmp_path / "sh")
    assert run("state", "init", shot)[0] == 0
    plate = tmp_path / "plate.mp4"
    plate.write_text("x")
    run("state", "record", shot, "plate", str(plate))
    run("state", "show", shot)  # read-only: not logged
    run("verify", str(tmp_path / "missing_####.png"), "--start", "1", "--end", "2", "--state", shot)
    evs = ev.read(shot)[0]
    starts = [e for e in evs if e["kind"] == "op.start"]
    ends = [e for e in evs if e["kind"] == "op.end"]
    assert [e["op"] for e in starts] == ["state init", "state record", "verify"]
    assert [e["op_id"] for e in starts] == [e["op_id"] for e in ends]
    assert [e["status"] for e in ends] == ["PASS", "PASS", "FAIL"]
    code, out = run("event", "note", shot, "rendering", "test", "frames", "--source", "cowork")
    assert code == 0 and ev.read(shot)[0][-1]["summary"] == "rendering test frames"
    code, out = run("event", "show", shot)
    assert "verify: FAIL" in out and "rendering test frames" in out


def test_preflight_reports(tmp_path):
    root = str(tmp_path / "root")
    os.makedirs(os.path.join(root, "_studio"))
    code, out = run("preflight", "--root", root, "--shot", str(tmp_path / "shot"))
    rep = json.loads(out)
    items = {i["item"]: i for i in rep["items"]}
    assert items["engine"]["status"] == "PASS" and items["shot_events"]["status"] == "PASS"
    assert items["settings"]["detail"]["values"]["research"] == "off"
    assert items["settings"]["detail"]["values"]["learning"] == "off"
    assert os.path.exists(rep["report"]) and rep["report"].endswith(rep["machine"] + ".json")
    with open(os.path.join(root, "_studio", "config.json"), "w") as f:
        f.write('{"research": "always"}')
    code, out = run("preflight", "--root", root, "--no-report")
    assert code == 1 and {i["item"]: i for i in json.loads(out)["items"]}["settings"]["status"] == "FAIL"
    if sys.platform != "darwin":
        code, out = run("preflight", "--require-native", "--no-report")
        assert code == 1 and {i["item"]: i for i in json.loads(out)["items"]}["machine"]["status"] == "FAIL"


def test_machine_kind():
    assert ev.machine_kind("darwin", "/Users/a", "mbp") == "mac"
    assert ev.machine_kind("linux", "/sessions/abc", "x") == "cowork-vm"
    assert ev.machine_kind("linux", "/home/u", "box") == "linux"
