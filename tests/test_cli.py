import json
import os
import re
import subprocess
import sys
import zipfile

from conftest import ROOT, SCRIPTS, make_png

VFX = os.path.join(SCRIPTS, "vfx.py")


def run(*args, cwd=None):
    r = subprocess.run([sys.executable, VFX, *args], capture_output=True, text=True, cwd=cwd, timeout=300)
    return r.returncode, r.stdout


def test_doctor():
    code, out = run("doctor")
    d = json.loads(out)
    assert code == 0 and d["ok"] and d["engine"]


def test_state_cli_roundtrip(tmp_path):
    shot = str(tmp_path / "sh010")
    assert run("state", "init", shot)[0] == 0
    plate = tmp_path / "plate.mp4"
    plate.write_text("x")
    assert run("state", "record", shot, "plate", str(plate))[0] == 0
    assert run("state", "check", shot, "plate")[0] == 0
    plate.write_text("y")
    code, out = run("state", "check", shot, "plate")
    assert code == 1 and "changed" in out
    code, out = run("status", shot)
    assert "STALE" in out
    assert run("state", "set", shot, "mode=wizard")[0] == 2


def test_verify_cli(tmp_path):
    for n in (1, 2, 4):
        make_png(str(tmp_path / f"{n:04d}.png"))
    code, out = run("verify", str(tmp_path / "####.png"), "--start", "1", "--end", "4")
    assert code == 1 and json.loads(out)["missing"] == "3"


def test_package_and_run_from_zip(tmp_path):
    z = str(tmp_path / "skill.zip")
    assert run("package", z)[0] == 0
    names = zipfile.ZipFile(z).namelist()
    for must in ("blender-vfx/SKILL.md", "blender-vfx/scripts/vfx.py", "blender-vfx/scripts/vfxlib/state.py",
                 "blender-vfx/scripts/build_proxy.py", "blender-vfx/references/04-tracking.md"):
        assert must in names
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]
    zipfile.ZipFile(z).extractall(tmp_path / "x")
    r = subprocess.run([sys.executable, str(tmp_path / "x" / "blender-vfx" / "scripts" / "vfx.py"), "doctor"],
                       capture_output=True, text=True, timeout=300)
    assert json.loads(r.stdout)["ok"]


def test_versions_agree():
    plugin = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
    top = re.search(r"^## (\d+\.\d+\.\d+)", open(os.path.join(ROOT, "CHANGELOG.md")).read(), re.M).group(1)
    sys.path.insert(0, SCRIPTS)
    from vfxlib import __version__
    assert plugin["version"] == top == __version__


def test_skill_md_is_small_and_points_to_real_files():
    skill = os.path.join(ROOT, "skills", "blender-vfx")
    text = open(os.path.join(skill, "SKILL.md")).read()
    assert len(text.encode()) < 9000, "SKILL.md must stay small"
    assert text.startswith("---\nname: blender-vfx\n")
    for ref in set(re.findall(r"`((?:references|recipes|templates|scripts)/[\w./-]+)`", text)):
        assert os.path.exists(os.path.join(skill, ref)), ref
    for py in re.findall(r"`(\w+\.py)`", text):
        assert os.path.exists(os.path.join(skill, "scripts", py)), py
