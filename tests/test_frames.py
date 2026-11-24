import os
import struct

import pytest

from conftest import make_png
from vfxlib import frames as fr


def test_png_integrity(tmp_path):
    good = make_png(str(tmp_path / "a.png"))
    assert fr.check_file(good) is None
    data = open(good, "rb").read()
    for name, blob, want in [("trunc.png", data[:-10], "truncated"), ("crc.png", data[:40] + b"X" + data[41:], "bad CRC"),
                             ("empty.png", b"", "empty"), ("junk.png", b"hello", "not a PNG")]:
        p = tmp_path / name
        p.write_bytes(blob)
        assert want in fr.check_file(str(p))


def test_jpeg_integrity(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    p = str(tmp_path / "a.jpg")
    cv2.imwrite(p, np.full((32, 32, 3), 90, np.uint8))
    assert fr.check_file(p) is None
    data = open(p, "rb").read()
    (tmp_path / "b.jpg").write_bytes(data[: len(data) // 2])
    assert "truncated" in fr.check_file(str(tmp_path / "b.jpg"))


def _exr(path):
    """Minimal valid scanline EXR: 4x4, one HALF channel, no compression."""
    def attr(n, t, v):
        return n.encode() + b"\0" + t.encode() + b"\0" + struct.pack("<i", len(v)) + v
    hdr = attr("channels", "chlist", b"Y\0" + struct.pack("<iBBBBii", 1, 0, 0, 0, 0, 1, 1) + b"\0")
    hdr += attr("compression", "compression", b"\0")
    hdr += attr("dataWindow", "box2i", struct.pack("<iiii", 0, 0, 3, 3))
    hdr += attr("displayWindow", "box2i", struct.pack("<iiii", 0, 0, 3, 3))
    hdr += attr("lineOrder", "lineOrder", b"\0")
    hdr += attr("pixelAspectRatio", "float", struct.pack("<f", 1))
    hdr += attr("screenWindowCenter", "v2f", struct.pack("<ff", 0, 0))
    hdr += attr("screenWindowWidth", "float", struct.pack("<f", 1))
    head = b"\x76\x2f\x31\x01" + struct.pack("<I", 2) + hdr + b"\0"
    table_start = len(head)
    chunks, offs = b"", []
    pos = table_start + 8 * 4
    for y in range(4):
        c = struct.pack("<ii", y, 8) + b"\x00\x3c" * 4
        offs.append(pos)
        pos += len(c)
        chunks += c
    with open(path, "wb") as f:
        f.write(head + b"".join(struct.pack("<Q", o) for o in offs) + chunks)
    return path


def test_exr_integrity(tmp_path):
    p = _exr(str(tmp_path / "a.exr"))
    assert fr.check_file(p) is None
    data = open(p, "rb").read()
    (tmp_path / "t.exr").write_bytes(data[:-6])
    assert "truncated" in fr.check_file(str(tmp_path / "t.exr"))
    (tmp_path / "h.exr").write_bytes(data[:30])
    assert fr.check_file(str(tmp_path / "h.exr"))
    zeroed = bytearray(data)
    start = len(data) - 4 * 16 - 32  # first entry of the offset table
    zeroed[start:start + 8] = b"\0" * 8
    (tmp_path / "z.exr").write_bytes(bytes(zeroed))
    assert fr.check_file(str(tmp_path / "z.exr"))


def test_sequence_verify(tmp_path):
    d = tmp_path / "beauty"
    for n in range(1, 11):
        if n == 4:
            continue
        make_png(str(d / f"shot_{n:04d}.png"), value=1 if n == 8 else 120)
    with open(d / "shot_0006.png", "r+b") as f:
        f.truncate(30)
    (d / "shot_0007.png").write_bytes(b"")
    r = fr.verify_sequence(str(d / "shot_####.png"), 1, 10)
    assert r["missing"] == "4" and r["empty"] == "7" and r["corrupt_count"] == 1
    assert r["status"] == "failed"
    if r.get("pixel_check") is None:
        assert r["black"] == "8"
    assert r["rerender"] == "4,6-7"


def test_stale_frames_detected(tmp_path):
    d = tmp_path / "r"
    for n in (1, 2, 3):
        make_png(str(d / f"{n:04d}.png"))
    old = os.path.getmtime(d / "0002.png") - 3600
    os.utime(d / "0002.png", (old, old))
    r = fr.verify_sequence(str(d / "####.png"), 1, 3, since=old + 1800, pixels=False)
    assert r["not_from_this_job"] == "2" and r["rerender"] == "2"


def test_flicker():
    spikes, black = fr.flicker([0.5, 0.5, 0.8, 0.5, 0.5, 0.0005, 0.5])
    assert spikes == [2] and black == [5]
