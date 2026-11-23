"""Render a few frames at low cost and tile them into one contact sheet.

Usage:
  blender -b shot_v003.blend -P contact_sheet.py -- --frames 1,24,48,72,96,120 --pct 50 --samples 64
Or exec inside an MCP code call after setting sys.argv.

Renders each frame as PNG to <blend folder>/../comp/contact_<timestamp>/,
then builds contact.png with ffmpeg (tile filter) if ffmpeg is on PATH.
Restores every render setting it changed. Prints one JSON line.
One image to look at instead of many saves tokens and time.
"""
import argparse
import glob
import json
import math
import os
import shutil
import subprocess
import sys
import time

import bpy


def parse(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("--frames", required=True, help="comma list, e.g. 1,24,48")
    p.add_argument("--pct", type=int, default=50)
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--out", default="")
    return p.parse_args(argv)


def main(a):
    scene = bpy.context.scene
    r = scene.render
    frames = [int(f) for f in a.frames.split(",") if f.strip()]
    if a.out:
        out_dir = os.path.expanduser(a.out)
    else:
        base = os.path.dirname(bpy.data.filepath) or bpy.app.tempdir
        out_dir = os.path.join(base, "..", "comp", time.strftime("contact_%Y%m%d_%H%M%S"))
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    saved = {
        "pct": r.resolution_percentage, "path": r.filepath, "fmt": r.image_settings.file_format,
        "media": getattr(r.image_settings, "media_type", None),
        "depth": r.image_settings.color_depth, "frame": scene.frame_current,
        "film": r.film_transparent,
    }
    is_cycles = r.engine == "CYCLES"
    if is_cycles:
        saved["samples"] = scene.cycles.samples
        scene.cycles.samples = a.samples
    try:
        r.resolution_percentage = a.pct
        if saved["media"] is not None:
            r.image_settings.media_type = "IMAGE"
        r.image_settings.file_format = "PNG"
        r.image_settings.color_depth = "8"
        r.film_transparent = False
        for f in frames:
            scene.frame_set(f)
            r.filepath = os.path.join(out_dir, f"f_{f:05d}.png")
            bpy.ops.render.render(write_still=True)
    finally:
        r.resolution_percentage = saved["pct"]
        r.filepath = saved["path"]
        if saved["media"] is not None:
            r.image_settings.media_type = saved["media"]
        r.image_settings.file_format = saved["fmt"]
        r.image_settings.color_depth = saved["depth"]
        r.film_transparent = saved["film"]
        scene.frame_set(saved["frame"])
        if is_cycles:
            scene.cycles.samples = saved["samples"]

    sheet = None
    pngs = sorted(glob.glob(os.path.join(out_dir, "f_*.png")))
    if shutil.which("ffmpeg") and pngs:
        cols = min(3, len(pngs))
        rows = math.ceil(len(pngs) / cols)
        sheet = os.path.join(out_dir, "contact.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-pattern_type", "glob",
                        "-i", os.path.join(out_dir, "f_*.png"),
                        "-vf", f"scale=640:-2,tile={cols}x{rows}:padding=4", "-frames:v", "1", sheet],
                       check=False)
        if not os.path.exists(sheet):
            sheet = None
    print(json.dumps({"frames": frames, "folder": out_dir, "contact_sheet": sheet}, separators=(",", ":")))


if __name__ == "__main__":
    main(parse(sys.argv))
