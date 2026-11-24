"""Read a plate before tracking: camera move, blur, exposure, and the solve to use.

The move is only named when the evidence supports it. Too few frames, too
few features or matches, or disagreeing frame pairs give 'unknown' with the
reason, instead of a confident guess.

  locked    almost no image motion           -> 2D tracking only
  rotation  one homography explains 90%+ of consistent matches within 2 px -> Tripod solve (or a flat scene)
  parallax  real 3D parallax                 -> full camera solve
  unknown   not enough evidence              -> say why, track by hand or reshoot
"""
import glob
import os

MIN_PAIRS = 3           # motion needs at least this many usable frame pairs
MIN_MATCHES = 40        # per pair
MIN_FEATURES = 150      # median per frame
MIN_USABLE_SHARE = 0.6  # of attempted pairs
LOCKED_PX = 0.5         # median shift per sampled pair, at 960 px wide


def _frames(src, pattern, every, limit):
    import cv2
    if os.path.isdir(src):
        files = sorted(glob.glob(os.path.join(src, pattern)))
        info = {"frames": len(files), "fps": None}
        for n, i in enumerate(range(0, len(files), every)):
            if n >= limit:
                break
            img = cv2.imread(files[i], cv2.IMREAD_COLOR)
            if img is not None:
                yield info, i, img
        return
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        return
    info = {"frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), "fps": round(cap.get(cv2.CAP_PROP_FPS), 3)}
    i = n = 0
    while n < limit:
        ok, img = cap.read()
        if not ok:
            break
        if i % every == 0:
            n += 1
            yield info, i, img
        i += 1
    cap.release()


def _pair(k0, d0, k1, d1, shape):
    import cv2
    import numpy as np
    if d0 is None or d1 is None or len(k0) < 30 or len(k1) < 30:
        return {"usable": False, "why": "few features"}
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d0, d1)
    if len(m) < MIN_MATCHES:
        return {"usable": False, "why": "few matches", "matches": len(m)}
    p0 = np.float32([k0[x.queryIdx].pt for x in m])
    p1 = np.float32([k1[x.trainIdx].pt for x in m])
    shift = float(np.median(np.linalg.norm(p1 - p0, axis=1)))
    spread = float(min(np.ptp(p0, axis=0) / np.array(shape[::-1], dtype=np.float32)))
    if shift < LOCKED_PX:
        return {"usable": True, "shift": shift, "matches": len(m), "spread": spread, "kind": "still"}
    cv2.setRNGSeed(0)  # repeatable RANSAC
    H, hm = cv2.findHomography(p0, p1, cv2.RANSAC, 2.0, maxIters=4000, confidence=0.999)
    F, fm = cv2.findFundamentalMat(p0, p1, cv2.FM_RANSAC, 1.0, 0.999)
    if H is None or hm is None:
        return {"usable": False, "why": "no consistent motion", "matches": len(m)}
    inl = hm.ravel().astype(bool)
    if inl.sum() >= 8:  # least-squares refit on the inliers: steadier than the RANSAC sample
        H2, _ = cv2.findHomography(p0[inl], p1[inl], 0)
        H = H2 if H2 is not None else H
    resid = np.linalg.norm(cv2.perspectiveTransform(p0.reshape(-1, 1, 2), H).reshape(-1, 2) - p1, axis=1)
    # judge only geometrically consistent matches (epipolar inliers), so mismatches don't count
    good = fm.ravel().astype(bool) if fm is not None and fm.shape[0] == len(m) else np.ones(len(m), bool)
    if good.sum() < MIN_MATCHES // 2:
        return {"usable": False, "why": "few consistent matches", "matches": len(m)}
    # ORB keypoints are only good to about 1 px at 960 wide, so 2 px counts as "explained"
    explained = float((resid[good] < 2.0).mean())
    unexplained = float((resid[good] > 3.0).mean())
    if explained >= 0.9:
        kind = "rotation"
    elif unexplained >= 0.15:
        kind = "parallax"
    else:
        kind = "unclear"
    h_in, f_in, res_med = explained, float(good.mean()), float(np.median(resid[good]))
    return {"usable": True, "shift": shift, "matches": len(m), "spread": spread, "kind": kind,
            "h_explained": h_in, "consistent": f_in, "h_resid": res_med}


def classify(pairs, attempted, feat_median):
    """Decide the move from per-pair evidence. Returns (motion, confidence, reasons)."""
    usable = [p for p in pairs if p["usable"]]
    reasons = []
    if attempted < MIN_PAIRS:
        reasons.append(f"only {attempted} frame pairs sampled (need {MIN_PAIRS}+); clip too short or --every too big")
    if feat_median < MIN_FEATURES:
        reasons.append(f"median {int(feat_median)} features per frame (want {MIN_FEATURES}+); low texture, blur or darkness")
    if attempted and len(usable) / attempted < MIN_USABLE_SHARE:
        reasons.append(f"only {len(usable)} of {attempted} pairs matched reliably")
    if len(usable) < MIN_PAIRS:
        return "unknown", "none", reasons or [f"only {len(usable)} usable pairs"]
    if reasons:
        return "unknown", "none", reasons
    kinds = [p["kind"] for p in usable]
    still = kinds.count("still") / len(kinds)
    moving = [k for k in kinds if k != "still"]
    if still >= 0.8:
        conf = "high" if still == 1.0 else "medium"
        return "locked", conf, [f"{round(still * 100)} percent of pairs show no motion"]
    par = moving.count("parallax") / len(moving)
    rot = moving.count("rotation") / len(moving)
    unclear = moving.count("unclear") / len(moving)
    if par >= 0.5:
        return "parallax", "high" if par >= 0.75 else "medium", [f"{round(par * 100)} percent of moving pairs show parallax"]
    if rot >= 0.75 and par < 0.15:
        return "rotation", "medium" if par == 0 else "low", [
            f"{round(rot * 100)} percent of moving pairs fit a pure rotation",
            "a flat scene (wall, screen, distant view) also looks like rotation; if the camera changed position, use a full solve"]
    if par >= 0.25:
        return "parallax", "low", [f"mixed evidence: {round(par * 100)} percent parallax, {round(rot * 100)} percent rotation"]
    return "unknown", "none", [f"pairs disagree ({round(rot * 100)} percent rotation, {round(par * 100)} percent parallax, "
                               f"{round(unclear * 100)} percent unclear)"]


SOLVE = {"locked": "No camera solve; 2D tracking only",
         "rotation": "Tripod solve; depth cannot be recovered",
         "parallax": "Full camera solve",
         "unknown": "Not enough evidence to choose. Track a few markers by hand and try a full solve, or reshoot"}


def analyse(src, pattern="*.png", every=4, limit=300):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {"error": "needs numpy and opencv-python (pip install numpy opencv-python-headless)"}
    orb = cv2.ORB_create(1500)
    sharp, mean, hi, lo, feats, pairs = [], [], [], [], [], []
    prev, info, res, attempted = None, {}, None, 0
    for info, idx, img in _frames(src, pattern, every, limit):
        res = res or [img.shape[1], img.shape[0]]
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        s = 960 / g.shape[1]
        g = cv2.resize(g, (960, max(1, int(g.shape[0] * s))), interpolation=cv2.INTER_AREA)
        sharp.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))
        mean.append(float(g.mean() / 255))
        hi.append(float((g >= 250).mean()))
        lo.append(float((g <= 5).mean()))
        k, d = orb.detectAndCompute(g, None)
        feats.append(len(k))
        if prev is not None:
            attempted += 1
            pairs.append(_pair(prev[0], prev[1], k, d, g.shape))
        prev = (k, d)
    if res is None:
        return {"error": f"no frames read from {src}"}
    feat_med = float(np.median(feats))
    motion, conf, why = classify(pairs, attempted, feat_med)
    usable = [p for p in pairs if p["usable"]]
    med_sharp = float(np.median(sharp))
    blurry = [i for i, s in enumerate(sharp) if s < 0.35 * med_sharp]
    warnings = []
    if blurry:
        warnings.append(f"{len(blurry)} of {len(sharp)} samples much blurrier than the rest; expect weak tracks there")
    if max(hi) > 0.05:
        warnings.append("over 5 percent of pixels clipped white on some frames")
    if float(np.median(mean)) < 0.12:
        warnings.append("dark plate; grade a brighter copy for tracking only")
    if usable and float(np.median([p["spread"] for p in usable])) < 0.5:
        warnings.append("features bunched in part of the frame; add manual markers across the image")
    return {"source": src, "resolution": res, "fps": info.get("fps"), "frames": info.get("frames"),
            "sampled": len(sharp), "every": every, "motion": motion, "confidence": conf, "evidence": why,
            "recommended_solve": SOLVE[motion], "pairs_usable": f"{len(usable)}/{attempted}",
            "features_median": int(feat_med),
            "shift_px_median": round(float(np.median([p["shift"] for p in usable])), 2) if usable else None,
            "sharpness_median": round(med_sharp, 1), "blurry_samples": blurry[:20],
            "exposure_median": round(float(np.median(mean)), 3), "clipped_white_max": round(max(hi), 4),
            "crushed_black_max": round(max(lo), 4), "warnings": warnings}
