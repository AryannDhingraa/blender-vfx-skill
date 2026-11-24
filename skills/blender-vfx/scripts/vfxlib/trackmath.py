"""Camera-solve maths with numpy: projection, triangulation, per-frame
reprojection, holdout scoring and coverage over time.

Conventions: Blender camera matrices are camera-to-world, looking down -Z
with +Y up. Image coordinates here are pixels with the origin top-left.
Lens distortion: Blender's polynomial model (k1, k2, k3) on normalised coords.
"""
import numpy as np

FLIP = np.diag([1.0, -1.0, -1.0])


def world_to_cam(M):
    M = np.asarray(M, dtype=float)
    R_cw = M[:3, :3].T
    return FLIP @ R_cw, FLIP @ (-R_cw @ M[:3, 3])


def _factor(x, k):
    r2 = (x ** 2).sum(axis=-1, keepdims=True)
    return 1 + k[0] * r2 + k[1] * r2 ** 2 + k[2] * r2 ** 3


def distort(xn, k):
    return xn * _factor(xn, k) if any(k) else xn


def undistort(xd, k, iters=20):
    if not any(k):
        return xd
    x = xd.copy()
    for _ in range(iters):
        x = xd / _factor(x, k)
    return x


def project(X, M, f, cx, cy, k=(0, 0, 0)):
    """World points (N,3) -> pixels (N,2) and depth (N,). Depth <= 0 is behind the camera."""
    R, t = world_to_cam(M)
    Xc = np.atleast_2d(X) @ R.T + t
    z = Xc[:, 2]
    xn = Xc[:, :2] / np.where(np.abs(z) < 1e-9, 1e-9, z)[:, None]
    xd = distort(xn, k)
    return np.column_stack([f * xd[:, 0] + cx, f * xd[:, 1] + cy]), z


def triangulate(Ms, uv, f, cx, cy, k=(0, 0, 0)):
    """Linear (DLT) triangulation of one point seen by several cameras."""
    xn = undistort((np.asarray(uv, float) - [cx, cy]) / f, k)
    rows = []
    for M, (x, y) in zip(Ms, xn):
        R, t = world_to_cam(M)
        P = np.hstack([R, t[:, None]])
        rows.append(x * P[2] - P[0])
        rows.append(y * P[2] - P[1])
    _, _, vt = np.linalg.svd(np.asarray(rows))
    Xh = vt[-1]
    return Xh[:3] / Xh[3] if abs(Xh[3]) > 1e-12 else None


def reproj_errors(X, Ms, uv, f, cx, cy, k=(0, 0, 0)):
    errs = []
    for M, p in zip(Ms, uv):
        q, z = project(X, M, f, cx, cy, k)
        errs.append(float(np.linalg.norm(q[0] - p)) if z[0] > 0 else float("inf"))
    return errs


def pct(vals, p):
    vals = [v for v in vals if np.isfinite(v)]
    return round(float(np.percentile(vals, p)), 3) if vals else None


def spikes(series, min_px=0.5):
    """Frames whose mean error jumps well above the shot's usual level (jitter or sliding)."""
    keys = sorted(series)
    vals = np.array([series[k] for k in keys])
    if len(vals) < 5:
        return []
    med = np.median(vals)
    mad = np.median(np.abs(vals - med)) or 1e-6
    return [k for k, v in zip(keys, vals) if v > med + 4 * 1.4826 * mad and v > min_px]


def coverage(points_by_frame, cells=3):
    """{frame: [(x,y) normalised 0..1]} -> {frame: occupied cells of a cells x cells grid}"""
    out = {}
    for fr, pts in points_by_frame.items():
        occ = {(min(cells - 1, max(0, int(x * cells))), min(cells - 1, max(0, int(y * cells)))) for x, y in pts}
        out[fr] = len(occ)
    return out
