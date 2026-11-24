import hashlib
import io
import json
import os
import zipfile

import pytest

from vfxlib import assets, hardware

PH_LIST = {
    "Barrel_01": {"name": "Barrel 01", "tags": ["barrel", "rusty", "metal"], "categories": ["props"], "type": 2,
                  "polycount": 2682, "max_resolution": [8192, 8192], "dimensions": [560, 560, 880],
                  "download_count": 50000, "authors": {"A": "All"}},
    "Mega_Statue": {"name": "Mega Statue", "tags": ["statue", "metal"], "categories": ["props"], "type": 2,
                    "polycount": 4_000_000, "max_resolution": [4096, 4096], "download_count": 10},
    "Chair": {"name": "Chair", "tags": ["wood"], "categories": ["furniture"], "type": 2, "polycount": 900,
              "max_resolution": [1024, 1024], "download_count": 99999},
}


def test_budget_tiers():
    assert hardware.budget_for(vram=4, gpu_list=[{"name": "GeForce GTX 1650", "vram_gb": 4, "vendor": "nvidia"}])["tier"] == "nvidia"
    b = hardware.budget_for(gpu_list=[{"name": "Apple M3 Pro", "unified": True, "vendor": "apple"}], ram=18)
    assert b["tier"] == "apple-silicon" and b["texture_res"] == "4k"
    assert hardware.budget_for(ram=8)["tier"] == "cpu"


def test_search_ranks_and_flags_heavy(monkeypatch):
    monkeypatch.setattr(assets, "_json", lambda url: PH_LIST)
    budget = hardware.budget_for(vram=4)
    r = assets.search("rusty metal barrel", "model", budget, limit=5)
    ids = [o["id"] for o in r["options"]]
    assert ids[0] == "Barrel_01" and "Chair" not in ids
    heavy = next(o for o in r["options"] if o["id"] == "Mega_Statue")
    assert heavy["suitability"] == "too heavy" and ids[-1] == "Mega_Statue"
    o = r["options"][0]
    for k in ("thumbnail", "page", "licence", "polycount", "max_res", "suggested_res", "size_m", "option"):
        assert k in o
    assert o["size_m"] == [0.56, 0.56, 0.88] and o["licence"] == "CC0"


def test_no_match_offers_procedural(monkeypatch):
    monkeypatch.setattr(assets, "_json", lambda url: PH_LIST)
    r = assets.search("spaceship", "model", hardware.budget_for(vram=8))
    assert not r["options"] and "procedural" in r["fallback"]


def test_download_needs_approval(tmp_path):
    r = assets.download("polyhaven", "Barrel_01", "model", "2k", str(tmp_path))
    assert r["status"] == "refused"
    assert not os.listdir(tmp_path)


def test_checksum_and_size_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "_get", lambda url, timeout=0, retries=0: b"abc")
    assets._fetch_to("u", str(tmp_path / "ok.bin"), hashlib.md5(b"abc").hexdigest(), 3)
    with pytest.raises(RuntimeError):
        assets._fetch_to("u", str(tmp_path / "bad.bin"), "0" * 32, 3)
    with pytest.raises(RuntimeError):
        assets._fetch_to("u", str(tmp_path / "bad.bin"), None, 99)
    assert not (tmp_path / "bad.bin").exists()


def test_zip_path_traversal_refused(tmp_path):
    zp = tmp_path / "evil.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("../escape.txt", "x")
    with pytest.raises(RuntimeError):
        assets._safe_extract(str(zp), str(tmp_path / "out"))
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.skipif(not os.environ.get("VFX_LIVE"), reason="set VFX_LIVE=1 to hit the real asset APIs")
def test_live_search_and_download(tmp_path):
    b = hardware.budget_for(vram=4)
    r = assets.search("barrel", "model", b, 3)
    assert r["options"] and r["options"][0]["thumbnail"].startswith("https://")
    h = assets.search("cloudy sky", "hdri", b, 3)["options"][0]
    d = assets.download("polyhaven", h["id"], "hdri", "1k", str(tmp_path), approved=True,
                        licence_log=str(tmp_path / "lic.md"))
    assert d["status"] == "ok" and "CC0" in open(tmp_path / "lic.md").read()
