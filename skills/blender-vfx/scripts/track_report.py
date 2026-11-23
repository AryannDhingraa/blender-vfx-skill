"""Camera tracking report: is this solve actually trustworthy?

Usage: blender -b shot.blend -P track_report.py   (or exec in an MCP call)

Read-only. For every movie clip prints one JSON line with: solve error,
median and 95th percentile track error, tracks per frame (weakest frames),
spread of tracks across the image (3x3 grid), track lifespans, and flags.
A low average error alone does not prove a good solve; check the flags.
"""
import json

import bpy


def pct(vals, p):
    if not vals:
        return None
    v = sorted(vals)
    return round(v[min(len(v) - 1, int(p / 100 * len(v)))], 3)


def report(clip):
    tr = clip.tracking
    rec = tr.reconstruction
    start = clip.frame_start
    end = start + clip.frame_duration - 1
    per_frame = {f: 0 for f in range(start, end + 1)}
    grid = [0] * 9
    errors, lifespans = [], []
    for t in tr.tracks:
        if t.has_bundle:
            errors.append(t.average_error)
        live = [m for m in t.markers if not m.mute]
        if not live:
            continue
        frames = [m.frame for m in live]
        lifespans.append(max(frames) - min(frames) + 1)
        for m in live:
            if m.frame in per_frame:
                per_frame[m.frame] += 1
        mid = live[len(live) // 2].co
        gx = min(2, max(0, int(mid[0] * 3)))
        gy = min(2, max(0, int(mid[1] * 3)))
        grid[gy * 3 + gx] += 1

    weakest = sorted(per_frame.items(), key=lambda kv: kv[1])[:5]
    flags = []
    if not rec.is_valid:
        flags.append("no valid camera solve")
    elif rec.average_error > 0.3:
        flags.append(f"solve error {rec.average_error:.2f} px is above 0.3")
    if weakest and weakest[0][1] < 8:
        flags.append(f"only {weakest[0][1]} tracks on frame {weakest[0][0]} (want 8+)")
    empty_cells = sum(1 for g in grid if g == 0)
    if empty_cells >= 3:
        flags.append(f"{empty_cells} of 9 image regions have no tracks; spread markers wider")
    p95 = pct(errors, 95)
    if p95 is not None and p95 > 1.0:
        flags.append(f"worst 5 percent of tracks above {p95} px; clean or delete them and re-solve")
    short = sum(1 for l in lifespans if l < 10)
    if lifespans and short / len(lifespans) > 0.5:
        flags.append("most tracks live under 10 frames; solve may drift")
    if clip.tracking.camera.focal_length <= 0:
        flags.append("focal length not set")

    return {
        "clip": clip.name, "frames": [start, end],
        "sensor_mm": round(tr.camera.sensor_width, 2), "focal_mm": round(tr.camera.focal_length, 2),
        "solve_valid": rec.is_valid, "solve_error": round(rec.average_error, 3) if rec.is_valid else None,
        "tracks": len(tr.tracks), "bundled": len(errors),
        "track_error_median": pct(errors, 50), "track_error_p95": p95,
        "weakest_frames": weakest, "grid_3x3": grid,
        "lifespan_median": pct(lifespans, 50),
        "flags": flags,
        "verdict": "ok" if not flags else "check flags before building on this solve",
    }


REPORT = json.dumps([report(c) for c in bpy.data.movieclips], separators=(",", ":"))
print(REPORT)
