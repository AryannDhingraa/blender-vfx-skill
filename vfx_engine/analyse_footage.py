"""Analyse a plate before tracking: what kind of shot is it, and what will hurt?

Usage:
  python3 analyse_footage.py clip.mp4
  python3 analyse_footage.py plates/ --pattern "*.png" --every 4

Needs: opencv-python (or opencv-python-headless) and numpy.
Prints one JSON line: resolution, fps, frame count, sharpness and exposure
per sampled frame (summarised), the camera motion type, and a recommended
solve. Read-only.

Motion type is decided from how well a homography (pure rotation or a flat
scene) explains feature motion between sampled frames, versus a fundamental
matrix (real 3D parallax):
  locked     almost no motion                -> 2D tracking only
  rotation   homography explains the motion  -> Tripod solve
  parallax   homography leaves big residuals -> full camera solve
"""
import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np


def frames_from(src, pattern, every, limit=400):
    if os.path.isdir(src):
        files = sorted(glob.glob(os.path.join(src, pattern)))
        info = {"frames": len(files), "fps": None}
        for i in range(0, len(files), every):
            img = cv2.imread(files[i], cv2.IMREAD_COLOR)
            if img is not None:
                yield info, i, img
            if i // every >= limit:
                break
        return
    cap = cv2.VideoCapture(src)
    info = {"frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), "fps": round(cap.get(cv2.CAP_PROP_FPS), 3)}
    i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if i % every == 0:
            yield info, i, img
        i += 1
    cap.release()


def gray_small(img, width=960):
    h, w = img.shape[:2]
    s = width / w
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (width, int(h * s)), interpolation=cv2.INTER_AREA), s


def motion_pair(g0, g1, orb):
    k0, d0 = orb.detectAndCompute(g0, None)
    k1, d1 = orb.detectAndCompute(g1, None)
    if d0 is None or d1 is None or len(k0) < 30 or len(k1) < 30:
        return None
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d0, d1)
    if len(m) < 30:
        return None
    p0 = np.float32([k0[x.queryIdx].pt for x in m])
    p1 = np.float32([k1[x.trainIdx].pt for x in m])
    shift = float(np.median(np.linalg.norm(p1 - p0, axis=1)))
    H, hm = cv2.findHomography(p0, p1, cv2.RANSAC, 2.0)
    F, fm = cv2.findFundamentalMat(p0, p1, cv2.FM_RANSAC, 1.0, 0.99)
    h_in = float(hm.mean()) if hm is not None else 0.0
    f_in = float(fm.mean()) if fm is not None else 0.0
    spread = np.ptp(p0, axis=0) / np.array(g0.shape[::-1], dtype=np.float32)
    return {"shift_px": shift, "h_inliers": h_in, "f_inliers": f_in, "matches": len(m),
            "spread": float(min(spread))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--pattern", default="*.png")
    ap.add_argument("--every", type=int, default=4, help="analyse every Nth frame")
    a = ap.parse_args()

    orb = cv2.ORB_create(1500)
    sharp, mean, clip_hi, clip_lo, pairs = [], [], [], [], []
    prev = None
    info, res = {}, None
    for info, idx, img in frames_from(a.src, a.pattern, a.every):
        res = res or [img.shape[1], img.shape[0]]
        g, _ = gray_small(img)
        sharp.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))
        mean.append(float(g.mean() / 255))
        clip_hi.append(float((g >= 250).mean()))
        clip_lo.append(float((g <= 5).mean()))
        if prev is not None:
            r = motion_pair(prev, g, orb)
            if r:
                pairs.append(r)
        prev = g
    if res is None:
        print(json.dumps({"error": "no frames read"}))
        return 1

    med_sharp = float(np.median(sharp))
    blurry = [i for i, s in enumerate(sharp) if s < 0.35 * med_sharp]
    shift = float(np.median([p["shift_px"] for p in pairs])) if pairs else 0.0
    h_in = float(np.median([p["h_inliers"] for p in pairs])) if pairs else 1.0
    f_in = float(np.median([p["f_inliers"] for p in pairs])) if pairs else 1.0
    moving = [p for p in pairs if p["shift_px"] >= 0.5]
    par = [p for p in moving if p["h_inliers"] < 0.8 or p["f_inliers"] > p["h_inliers"] + 0.05]
    par_share = len(par) / len(moving) if moving else 0.0
    if shift < 0.5:
        motion, solve = "locked", "No camera solve; 2D tracking only"
    elif par_share >= 0.25:
        motion, solve = "parallax", "Full camera solve"
    elif h_in >= 0.85 and h_in >= f_in - 0.05:
        motion, solve = "rotation", "Tripod solve (pan or tilt, or a flat scene); depth cannot be recovered"
    else:
        motion, solve = "parallax", "Full camera solve"

    warnings = []
    if motion == "rotation" and par_share > 0:
        warnings.append(f"{round(par_share*100)} percent of moves show parallax; a flat surface (screen, wall) may be hiding camera movement. Try a full solve too and compare")
    if blurry:
        warnings.append(f"{len(blurry)} of {len(sharp)} sampled frames much blurrier than the rest (motion blur or focus); expect weak tracks there")
    if max(clip_hi) > 0.05:
        warnings.append("more than 5 percent of pixels clipped white on some frames; detail lost in highlights")
    if float(np.median(mean)) < 0.12:
        warnings.append("dark plate; tracking needs contrast, consider a brighter grade for tracking only")
    if pairs and float(np.median([p["spread"] for p in pairs])) < 0.5:
        warnings.append("features bunched in part of the frame; add manual markers across the whole image")
    if pairs and min(p["matches"] for p in pairs) < 60:
        warnings.append("some frame pairs have few matching features; low texture or fast motion")

    print(json.dumps({
        "source": a.src, "resolution": res, "fps": info.get("fps"), "frames": info.get("frames"),
        "sampled": len(sharp), "every": a.every,
        "sharpness_median": round(med_sharp, 1), "blurry_samples": blurry[:20],
        "exposure_median": round(float(np.median(mean)), 3),
        "clipped_white_max": round(max(clip_hi), 4), "crushed_black_max": round(max(clip_lo), 4),
        "motion": motion, "median_shift_px_per_sample": round(shift, 2),
        "homography_inliers": round(h_in, 3), "fundamental_inliers": round(f_in, 3),
        "parallax_share": round(par_share, 2), "recommended_solve": solve, "warnings": warnings,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
