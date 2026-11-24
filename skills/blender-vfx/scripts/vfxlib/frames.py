"""Frame sequence verification: missing, empty, truncated or corrupt frames,
frames older than a job, black frames and brightness flicker.

Integrity checks are structural and need no libraries:
  PNG   signature, every chunk length and CRC, IEND present
  JPEG  start and end markers
  EXR   magic, header, offset table, last chunk fits inside the file
  TIFF  byte order mark and first IFD inside the file
Pixel checks (black, flicker) use OpenCV when installed.
"""
import glob
import os
import re
import struct
import zlib

from .common import compress_ranges

EXR_LINES = {0: 1, 1: 1, 2: 1, 3: 16, 4: 32, 5: 16, 6: 32, 7: 32, 8: 32, 9: 256}
FRAME_RE = re.compile(r"(\d+)(?=\.[A-Za-z0-9]+$)")


def check_png(f, size):
    if f.read(8) != b"\x89PNG\r\n\x1a\n":
        return "not a PNG"
    pos = 8
    while True:
        head = f.read(8)
        if len(head) < 8:
            return "truncated (no IEND)"
        length, ctype = struct.unpack(">I4s", head)
        if pos + 12 + length > size:
            return "truncated inside a chunk"
        data = f.read(length)
        crc = f.read(4)
        if len(crc) < 4 or zlib.crc32(ctype + data) & 0xFFFFFFFF != struct.unpack(">I", crc)[0]:
            return f"bad CRC in {ctype.decode('latin1')} chunk"
        pos += 12 + length
        if ctype == b"IEND":
            return None


def check_jpeg(f, size):
    if f.read(2) != b"\xff\xd8":
        return "not a JPEG"
    f.seek(max(0, size - 4096))
    tail = f.read().rstrip(b"\x00")
    return None if tail.endswith(b"\xff\xd9") else "truncated (no end marker)"


def _exr_headers(f, multipart):
    headers = []
    while True:
        attrs = {}
        while True:
            name = _cstr(f)
            if name == b"":
                break
            atype = _cstr(f)
            (n,) = struct.unpack("<i", f.read(4))
            if n < 0 or n > 1 << 24:
                raise ValueError("bad attribute size")
            attrs[name.decode("latin1")] = (atype.decode("latin1"), f.read(n))
        headers.append(attrs)
        if not multipart:
            return headers
        pos = f.tell()
        if f.read(1) == b"\x00":
            return headers
        f.seek(pos)


def _cstr(f, limit=256):
    b = bytearray()
    while len(b) < limit:
        c = f.read(1)
        if not c:
            raise ValueError("truncated header")
        if c == b"\x00":
            return bytes(b)
        b += c
    raise ValueError("bad header string")


def check_exr(f, size):
    if f.read(4) != b"\x76\x2f\x31\x01":
        return "not an EXR"
    (ver,) = struct.unpack("<I", f.read(4))
    tiled, deep, multi = bool(ver & 0x200), bool(ver & 0x800), bool(ver & 0x1000)
    try:
        headers = _exr_headers(f, multi)
    except (ValueError, struct.error):
        return "truncated or corrupt header"
    counts = []
    for h in headers:
        if "chunkCount" in h:
            counts.append(struct.unpack("<i", h["chunkCount"][1])[0])
            continue
        if tiled or deep:
            return None if not multi else "multipart file without chunkCount"
        try:
            xmin, ymin, xmax, ymax = struct.unpack("<iiii", h["dataWindow"][1])
            comp = h["compression"][1][0]
        except (KeyError, struct.error, IndexError):
            return "header missing dataWindow or compression"
        lines = EXR_LINES.get(comp)
        if lines is None:
            return None  # newer compression: header fine, offsets not checked
        counts.append(-(-(ymax - ymin + 1) // lines))
    table_end = f.tell() + 8 * sum(counts)
    if table_end > size:
        return "truncated offset table"
    offsets = [struct.unpack("<Q", f.read(8))[0] for _ in range(sum(counts))]
    if any(o == 0 for o in offsets):
        return "incomplete (unwritten chunks)"
    if any(o < table_end or o >= size for o in offsets):
        return "offset outside the file (truncated)"
    last = max(offsets)
    f.seek(last)
    head = f.read((4 if multi else 0) + (20 if tiled else 8))
    if deep or len(head) < 8:
        return None if deep else "truncated last chunk"
    (dsize,) = struct.unpack("<i", head[-4:])
    return None if last + len(head) + dsize <= size else "truncated last chunk"


def check_tiff(f, size):
    bom = f.read(4)
    if bom not in (b"II*\x00", b"MM\x00*"):
        return "not a TIFF"
    (ifd,) = struct.unpack("<I" if bom[:2] == b"II" else ">I", f.read(4))
    return None if 8 <= ifd < size else "first IFD outside the file (truncated)"


CHECKERS = {".png": check_png, ".jpg": check_jpeg, ".jpeg": check_jpeg, ".exr": check_exr,
            ".tif": check_tiff, ".tiff": check_tiff}


def check_file(path):
    """None if the file looks complete, else a short reason."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return "missing"
    if size == 0:
        return "empty"
    fn = CHECKERS.get(os.path.splitext(path)[1].lower())
    if fn is None:
        return None
    try:
        with open(path, "rb") as f:
            return fn(f, size)
    except (OSError, struct.error) as e:
        return f"unreadable ({e.__class__.__name__})"


def find_frames(pattern):
    """'renders/v004/beauty/####.exr', a glob, or a folder -> {frame: path}"""
    if os.path.isdir(pattern):
        files = [os.path.join(pattern, n) for n in os.listdir(pattern)
                 if os.path.splitext(n)[1].lower() in CHECKERS]
    else:
        files = glob.glob(re.sub(r"#+", "*", pattern))
    frames = {}
    for p in files:
        m = FRAME_RE.search(os.path.basename(p))
        if m and os.path.isfile(p):
            frames.setdefault(int(m.group(1)), p)
    return frames


def luma_series(paths):
    """Mean brightness per frame (0..1) via OpenCV, or None if unavailable."""
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    vals = []
    for p in paths:
        img = cv2.imread(p, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_ANYCOLOR)
        if img is None:
            vals.append(None)
            continue
        scale = {np.dtype(np.uint8): 255.0, np.dtype(np.uint16): 65535.0}.get(img.dtype, 1.0)
        img = img.astype(np.float32) / scale
        if img.ndim == 3:
            img = img[..., :3].mean(axis=2)
        vals.append(float(np.clip(img, 0, None)[::4, ::4].mean()))
    return vals


def flicker(vals, jump=0.06, floor=0.005):
    """Indexes whose brightness jumps against both neighbours, and black frames."""
    spikes, black = [], []
    for i, v in enumerate(vals):
        if v is not None and v < floor:
            black.append(i)
    for i in range(1, len(vals) - 1):
        a, b, c = vals[i - 1], vals[i], vals[i + 1]
        if None in (a, b, c) or i in black:
            continue
        ref = max((a + c) / 2, 1e-6)
        if abs(b - a) / ref > jump and abs(b - c) / ref > jump:
            spikes.append(i)
    return spikes, black


def verify_sequence(pattern, start=None, end=None, since=None, pixels=True):
    frames = find_frames(pattern)
    if start is None or end is None:
        if not frames:
            return {"type": "sequence", "status": "failed", "found": 0, "errors": ["no frames found"],
                    "rerender": ""}
        start = min(frames) if start is None else start
        end = max(frames) if end is None else end
    want = range(start, end + 1)
    missing, empty, corrupt, old = [], [], {}, []
    for n in want:
        p = frames.get(n)
        if p is None:
            missing.append(n)
            continue
        reason = check_file(p)
        if reason == "empty":
            empty.append(n)
        elif reason:
            corrupt[n] = reason
        elif since is not None and os.path.getmtime(p) < since - 1:
            old.append(n)
    res = {"type": "sequence", "range": [start, end], "expected": len(want),
           "found": sum(1 for n in want if n in frames), "missing": compress_ranges(missing),
           "empty": compress_ranges(empty), "corrupt": {compress_ranges([n]): r for n, r in list(corrupt.items())[:10]},
           "corrupt_count": len(corrupt), "not_from_this_job": compress_ranges(old)}
    bad = set(missing) | set(empty) | set(corrupt) | set(old)
    if pixels:
        good = [n for n in want if n in frames and n not in bad]
        vals = luma_series([frames[n] for n in good])
        if vals is None:
            res["pixel_check"] = "skipped (OpenCV not installed)"
        else:
            sp, bl = flicker(vals)
            res["black"] = compress_ranges([good[i] for i in bl])
            res["flicker"] = compress_ranges([good[i] for i in sp])
            res["unreadable"] = compress_ranges([good[i] for i, v in enumerate(vals) if v is None])
            bad |= {good[i] for i, v in enumerate(vals) if v is None}
    res["rerender"] = compress_ranges(bad)
    res["status"] = "ok" if not bad and not res.get("black") and not res.get("flicker") else "failed"
    return res
