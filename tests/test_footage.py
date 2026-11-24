import os

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
from vfxlib.footage import analyse, classify  # noqa: E402


def _texture(rng, w, h):
    img = (rng.random((h // 8, w // 8)) * 255).astype(np.uint8)
    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(cv2.GaussianBlur(img, (3, 3), 0), cv2.COLOR_GRAY2BGR)


def _clip(tmp_path, name, frames):
    d = tmp_path / name
    d.mkdir()
    for i, f in enumerate(frames):
        cv2.imwrite(str(d / f"{i:04d}.png"), f)
    return str(d)


def _shift(img, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REFLECT)


def test_locked(tmp_path):
    rng = np.random.default_rng(1)
    base = _texture(rng, 960, 540)
    fr = [np.clip(base + rng.normal(0, 2, base.shape), 0, 255).astype(np.uint8) for _ in range(24)]
    r = analyse(_clip(tmp_path, "locked", fr), every=2)
    assert r["motion"] == "locked" and r["confidence"] in ("high", "medium")


def test_rotation_pan(tmp_path):
    rng = np.random.default_rng(2)
    big = _texture(rng, 1600, 540)
    fr = [big[:, i * 12: i * 12 + 960].copy() for i in range(24)]
    r = analyse(_clip(tmp_path, "pan", fr), every=2)
    assert r["motion"] == "rotation", r


def test_parallax(tmp_path):
    rng = np.random.default_rng(3)
    bg, fg = _texture(rng, 1400, 540), _texture(rng, 1800, 540)
    fr = []
    for i in range(24):
        f = bg[:, i * 4: i * 4 + 960].copy()
        f[:, 480:] = fg[:, 480 + i * 22: 960 + i * 22]  # near layer moves 5x faster
        fr.append(f)
    r = analyse(_clip(tmp_path, "par", fr), every=2)
    assert r["motion"] == "parallax", r


def test_low_texture_is_unknown(tmp_path):
    rng = np.random.default_rng(4)
    fr = [np.full((540, 960, 3), 128, np.uint8) for _ in range(20)]
    r = analyse(_clip(tmp_path, "flat", fr), every=2)
    assert r["motion"] == "unknown" and r["confidence"] == "none"
    assert any("features" in e for e in r["evidence"])


def test_too_short_is_unknown(tmp_path):
    rng = np.random.default_rng(5)
    base = _texture(rng, 960, 540)
    r = analyse(_clip(tmp_path, "short", [base, _shift(base, 5, 0)]), every=1)
    assert r["motion"] == "unknown" and "pairs" in r["evidence"][0]


def test_disagreeing_pairs_are_unknown():
    pairs = [{"usable": True, "kind": k, "shift": 3} for k in ["rotation", "parallax", "unclear", "unclear", "rotation", "unclear"]]
    m, conf, why = classify(pairs, 6, 500)
    assert m == "unknown" and "disagree" in why[0]


def test_reads_video_file(tmp_path):
    rng = np.random.default_rng(6)
    base = _texture(rng, 640, 360)
    p = str(tmp_path / "clip.mp4")
    w = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*"mp4v"), 24, (640, 360))
    if not w.isOpened():
        pytest.skip("no mp4 writer in this OpenCV build")
    for i in range(30):
        w.write(base)
    w.release()
    r = analyse(p, every=3)
    assert r["fps"] == 24 and r["motion"] == "locked"
