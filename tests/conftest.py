import os
import struct
import subprocess
import sys
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "blender-vfx", "scripts")
sys.path.insert(0, SCRIPTS)


def make_png(path, w=16, h=8, value=128):
    raw = b"".join(b"\x00" + bytes([value]) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


_BPY = None


def bpy_python():
    """A Python that can import bpy (Blender as a module), or None."""
    global _BPY
    if _BPY is None:
        cand = os.environ.get("VFX_BPY_PYTHON") or sys.executable
        try:
            ok = subprocess.run([cand, "-c", "import bpy"], capture_output=True, timeout=120).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        _BPY = cand if ok else ""
    return _BPY or None


needs_bpy = pytest.mark.skipif(bpy_python() is None, reason="bpy (Blender as a Python module) not installed")


def run_blender(script_body, timeout=600):
    """Run Python code inside Blender (bpy module) in a fresh process; return stdout."""
    py = bpy_python()
    # exit right after the body: the bpy 4.2 module can crash during interpreter teardown
    # after glTF use (missing Draco library). Errors inside the body still exit with 1.
    body = script_body + "\nimport os as _os, sys as _sys\n_sys.stdout.flush()\n_os._exit(0)\n"
    r = subprocess.run([py, "-c", body], capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "VFX_SCRIPTS": SCRIPTS})
    if r.returncode != 0:
        raise AssertionError(f"Blender script failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return r.stdout
