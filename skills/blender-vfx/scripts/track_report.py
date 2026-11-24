"""Camera solve trust report. Run in Blender (headless or through MCP).

  blender -b shot.blend -P track_report.py
  blender -b shot.blend -P track_report.py -- --prepare-holdout 3   (marks holdouts, then save and re-solve)
  blender -b shot.blend -P track_report.py -- --restore-holdout

Read-only unless a holdout option is given. Per clip it prints one JSON line:
  - solve error, median and 95th percentile track error
  - tracks per frame and frames under 8 tracks
  - spread over time: frames where tracks cover 4 or fewer of 9 image regions
  - per-frame reprojection error and frames where it spikes (jitter, sliding)
  - holdout check: tracks with weight 0 (not used by the solve) are
    triangulated from the solved cameras and their error is compared
  - a self-check: our per-track error must match Blender's, or the per-frame
    and holdout numbers are withheld instead of being wrong
"""
import json
import os
import sys


def _engine():
    d = os.environ.get("VFX_SCRIPTS")
    if not d:
        try:
            d = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            d = None
    if d and d not in sys.path:
        sys.path.insert(0, d)


_engine()
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from vfxlib import trackmath as tm  # noqa: E402
from vfxlib.common import compress_ranges  # noqa: E402


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"prepare": None, "restore": False}
    if "--prepare-holdout" in argv:
        a["prepare"] = int(argv[argv.index("--prepare-holdout") + 1])
    a["restore"] = "--restore-holdout" in argv
    return a


def intrinsics(clip):
    cam = clip.tracking.camera
    W, H = clip.size
    f = cam.focal_length_pixels
    ppx, ppy = cam.principal_point_pixels
    k = (0.0, 0.0, 0.0)
    exact = True
    if cam.distortion_model == "POLYNOMIAL":
        k = (cam.k1, cam.k2, cam.k3)
    elif any(abs(getattr(cam, n, 0.0)) > 1e-9 for n in ("division_k1", "division_k2", "nuke_k1", "nuke_k2",
                                                        "brown_k1", "brown_k2", "brown_k3", "brown_k4")):
        exact = False
    if abs(cam.pixel_aspect - 1.0) > 1e-6:
        exact = False
    return W, H, f, ppx, H - ppy, k, exact


def prepare_holdout(clip, n):
    """Pick n long, well spread tracks and set their weight to 0."""
    cands = []
    for t in clip.tracking.tracks:
        live = [m for m in t.markers if not m.mute]
        if len(live) < 10 or t.weight == 0:
            continue
        mid = live[len(live) // 2].co
        cell = (min(2, int(mid[0] * 3)), min(2, int(mid[1] * 3)))
        cands.append((len(live), cell, t))
    cands.sort(key=lambda c: -c[0])
    picked, cells = [], set()
    for life, cell, t in cands:
        if cell not in cells:
            picked.append(t)
            cells.add(cell)
        if len(picked) == n:
            break
    for t in picked:
        t.weight = 0.0
    return [t.name for t in picked]


def report(clip):
    tr = clip.tracking
    rec = tr.reconstruction
    W, H, f, cx, cy, k, exact = intrinsics(clip)
    start, end = clip.frame_start, clip.frame_start + clip.frame_duration - 1
    cams = {c.frame: np.array(c.matrix) for c in rec.cameras} if rec.is_valid else {}

    per_frame, pts = {fr: 0 for fr in range(start, end + 1)}, {}
    bl_err, our_err, diffs, frame_err, lifespans, holdouts = [], [], [], {}, [], []
    for t in tr.tracks:
        live = [m for m in t.markers if not m.mute and start <= m.frame <= end]
        if not live:
            continue
        lifespans.append(live[-1].frame - live[0].frame + 1)
        for m in live:
            per_frame[m.frame] += 1
            pts.setdefault(m.frame, []).append((m.co[0], m.co[1]))
        if not cams:
            continue
        obs = [(cams[m.frame], (m.co[0] * W, (1 - m.co[1]) * H)) for m in live if m.frame in cams]
        if len(obs) < 2:
            continue
        Ms, uv = [o[0] for o in obs], np.array([o[1] for o in obs])
        if t.weight == 0:
            X = tm.triangulate(Ms, uv, f, cx, cy, k)
            if X is not None:
                e = tm.reproj_errors(X, Ms, uv, f, cx, cy, k)
                holdouts.append((t.name, float(np.median(e))))
            continue
        if not t.has_bundle:
            continue
        e = tm.reproj_errors(np.array(t.bundle), Ms, uv, f, cx, cy, k)
        bl_err.append(t.average_error)
        our_err.append(float(np.mean(e)))
        diffs.append(abs(our_err[-1] - t.average_error))
        for (M, _), m, ei in zip(obs, [m for m in live if m.frame in cams], e):
            frame_err.setdefault(m.frame, []).append(ei)

    model_ok = bool(diffs) and float(np.median(diffs)) <= max(0.25, 0.25 * float(np.median(bl_err)))
    flags = []
    if not rec.is_valid:
        flags.append("no valid camera solve")
    under8 = [fr for fr, n in per_frame.items() if n < 8]
    if under8:
        flags.append(f"{len(under8)} frames have fewer than 8 tracks ({compress_ranges(under8)[:60]})")
    cov = tm.coverage(pts)
    poor = [fr for fr in per_frame if cov.get(fr, 0) <= 4]
    if poor:
        flags.append(f"{len(poor)} frames have tracks in 4 or fewer of 9 image regions ({compress_ranges(poor)[:60]})")
    p50, p95 = tm.pct(bl_err, 50), tm.pct(bl_err, 95)
    if p95 is not None and p95 > 1.0:
        flags.append(f"worst 5 percent of tracks above {p95} px; clean them and re-solve")
    if lifespans and sum(1 for l in lifespans if l < 10) / len(lifespans) > 0.5:
        flags.append("most tracks live under 10 frames; the solve may drift")

    out = {"clip": clip.name, "frames": [start, end], "size": [W, H],
           "focal_mm": round(tr.camera.focal_length, 2), "sensor_mm": round(tr.camera.sensor_width, 2),
           "solve_valid": rec.is_valid, "solve_error": round(rec.average_error, 3) if rec.is_valid else None,
           "tracks": len(tr.tracks), "bundled": len(bl_err), "track_error_median": p50, "track_error_p95": p95,
           "min_tracks_per_frame": min(per_frame.values()) if per_frame else 0,
           "lifespan_median": tm.pct(lifespans, 50)}
    if rec.is_valid and bl_err:
        out["self_check"] = {"matches_blender": model_ok, "median_diff_px": round(float(np.median(diffs)), 3),
                             "exact_lens_model": exact}
        if model_ok:
            series = {fr: float(np.mean(v)) for fr, v in frame_err.items()}
            sp = tm.spikes(series)
            out["frame_error_p95"] = tm.pct(list(series.values()), 95)
            if sp:
                out["error_spike_frames"] = compress_ranges(sp)
                flags.append(f"reprojection error spikes on frames {compress_ranges(sp)[:60]}: check for jitter or sliding there")
        else:
            flags.append("projection self-check failed (lens model not matched); per-frame and holdout numbers withheld")
    if holdouts and model_ok:
        h_med = float(np.median([e for _, e in holdouts]))
        out["holdout"] = {"tracks": [n for n, _ in holdouts], "error_median": round(h_med, 3)}
        ref = p50 or 0.1
        if h_med > max(1.0, 3 * ref):
            flags.append(f"holdout tracks miss by {h_med:.2f} px (solve tracks {ref:.2f}): the solve fits its own tracks "
                         "but not the scene; retrack or add depth variety")
    elif rec.is_valid and not holdouts:
        out["holdout"] = "not run: use --prepare-holdout 3, solve again, then run this report"
    hard = [fl for fl in flags if fl.startswith(("no valid", "holdout", "projection"))]
    out["flags"] = flags
    out["trust"] = "low" if hard or not rec.is_valid else ("medium" if flags else "high")
    return out


def main():
    a = _args()
    res = []
    for clip in bpy.data.movieclips:
        if a["prepare"]:
            res.append({"clip": clip.name, "holdout_tracks": prepare_holdout(clip, a["prepare"]),
                        "next": "save a new .blend version, solve again, then run the report"})
        elif a["restore"]:
            n = 0
            for t in clip.tracking.tracks:
                if t.weight == 0:
                    t.weight, n = 1.0, n + 1
            res.append({"clip": clip.name, "restored": n})
        else:
            res.append(report(clip))
    print(json.dumps(res, separators=(",", ":")))
    return res


REPORT = main()
