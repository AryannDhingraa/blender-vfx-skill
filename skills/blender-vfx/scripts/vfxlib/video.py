"""Checks for a finished video file, using ffprobe and ffmpeg."""
import json
import re
import shutil
import subprocess

from .frames import flicker
from .common import compress_ranges


def _run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def verify_video(path, fps=None, seconds=None, pixels=True):
    if not shutil.which("ffprobe"):
        return {"type": "video", "status": "failed", "errors": ["ffprobe not found"]}
    r = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
              "stream=width,height,r_frame_rate,nb_read_frames,codec_name,pix_fmt:format=duration",
              "-of", "json", path])
    try:
        info = json.loads(r.stdout or "{}")
        s = info["streams"][0]
    except (ValueError, KeyError, IndexError):
        return {"type": "video", "status": "failed", "errors": ["no readable video stream", r.stderr.strip()[:200]]}
    num, den = (s.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    res = {"type": "video", "width": s.get("width"), "height": s.get("height"),
           "fps": round(float(num) / float(den or 1), 3), "frames": int(s.get("nb_read_frames") or 0),
           "codec": s.get("codec_name"), "pix_fmt": s.get("pix_fmt"),
           "duration": round(float(info.get("format", {}).get("duration") or 0), 3), "errors": []}
    if r.stderr.strip():
        res["errors"].append("decoder errors: " + r.stderr.strip().splitlines()[0][:160])
    if fps and seconds:
        res["expected_frames"] = round(fps * seconds)
        if res["frames"] != res["expected_frames"]:
            res["errors"].append(f"frame count {res['frames']} != expected {res['expected_frames']}")
    if pixels and shutil.which("ffmpeg"):
        r = _run(["ffmpeg", "-v", "error", "-i", path, "-vf",
                  "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"])
        vals = [float(v) / 255.0 for v in re.findall(r"YAVG=([0-9.]+)", r.stdout + r.stderr)]
        sp, bl = flicker(vals, floor=1.0 / 255)
        res["black"] = compress_ranges([i + 1 for i in bl])
        res["flicker"] = compress_ranges([i + 1 for i in sp])
        if res["black"]:
            res["errors"].append(f"black frames {res['black']}")
        if res["flicker"]:
            res["errors"].append(f"brightness spikes at {res['flicker']}")
    res["status"] = "ok" if not res["errors"] else "failed"
    return res
