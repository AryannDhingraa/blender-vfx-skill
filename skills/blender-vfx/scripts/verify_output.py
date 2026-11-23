"""Check a rendered video file or image sequence before calling a shot done.

Usage:
  python3 verify_output.py final.mov --fps 24 --seconds 12
  python3 verify_output.py renders/shot010/v003/ --pattern "*.exr"

Needs ffprobe/ffmpeg on PATH for video files and for brightness checks.
Prints a short report: frame count, resolution, missing or duplicate
frame numbers, and frames whose average brightness jumps against both
neighbours (dropped samples, mixed-machine renders, black frames).
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

JUMP = 0.06  # relative brightness jump that counts as a spike


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def video_info(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames,duration",
             "-of", "json", path])
    s = json.loads(r.stdout or "{}").get("streams", [{}])[0]
    num, den = (s.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    return {"width": s.get("width"), "height": s.get("height"), "fps": round(fps, 3),
            "frames": int(s.get("nb_read_frames", 0) or 0),
            "duration": float(s.get("duration", 0) or 0)}


def brightness_series(source, is_sequence):
    inp = ["-i", source]
    if is_sequence:
        inp = ["-pattern_type", "glob", "-i", source]
    r = run(["ffmpeg", "-v", "error", *inp, "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
             "-f", "null", "-"])
    vals = [float(v) for v in re.findall(r"YAVG=([0-9.]+)", r.stderr + r.stdout)]
    return vals


def spikes(vals):
    out = []
    for i in range(1, len(vals) - 1):
        a, b, c = vals[i - 1], vals[i], vals[i + 1]
        ref = max((a + c) / 2, 1e-6)
        if abs(b - a) / ref > JUMP and abs(b - c) / ref > JUMP:
            out.append(i)
    black = [i for i, v in enumerate(vals) if v < 1.0]
    return out, black


def check_sequence(folder, pattern):
    files = sorted(glob.glob(os.path.join(folder, pattern)))
    nums = []
    for f in files:
        m = re.findall(r"(\d+)", os.path.basename(f))
        if m:
            nums.append(int(m[-1]))
    missing = []
    if nums:
        have = set(nums)
        missing = [n for n in range(min(nums), max(nums) + 1) if n not in have]
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    return files, nums, missing, dupes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--pattern", default="*.png")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--no-brightness", action="store_true")
    a = ap.parse_args()

    report = {}
    if os.path.isdir(a.target):
        files, nums, missing, dupes = check_sequence(a.target, a.pattern)
        report.update({"type": "sequence", "frames": len(files),
                       "range": [min(nums), max(nums)] if nums else None,
                       "missing": missing[:20], "duplicates": dupes[:20]})
        src, seq = os.path.join(a.target, a.pattern), True
    else:
        report.update({"type": "video", **video_info(a.target)})
        src, seq = a.target, False

    if a.fps and a.seconds:
        expected = round(a.fps * a.seconds)
        report["expected_frames"] = expected
        report["frame_count_ok"] = report.get("frames") == expected

    if not a.no_brightness:
        vals = brightness_series(src, seq)
        if vals:
            sp, black = spikes(vals)
            report["brightness_spikes"] = [i + 1 for i in sp[:20]]  # 1-based position in the sequence
            report["black_frames"] = [i + 1 for i in black[:20]]
        else:
            report["brightness_check"] = "skipped (ffmpeg could not read frames; EXR needs an ffmpeg build with EXR support)"

    print(json.dumps(report, separators=(",", ":")))
    bad = report.get("missing") or report.get("duplicates") or report.get("brightness_spikes") \
        or report.get("black_frames") or report.get("frame_count_ok") is False
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
