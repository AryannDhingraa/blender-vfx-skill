import math

import pytest

np = pytest.importorskip("numpy")
from vfxlib import trackmath as tm  # noqa: E402


def _cam(pos, yaw):
    """Blender camera looking along +Y rotated by yaw, camera-to-world matrix."""
    rx = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)  # rotate 90 deg about X: looks along +Y
    c, s = math.cos(yaw), math.sin(yaw)
    rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    M = np.eye(4)
    M[:3, :3] = rz @ rx
    M[:3, 3] = pos
    return M


def test_project_triangulate_roundtrip():
    f, cx, cy = 1500.0, 960.0, 540.0
    X = np.array([0.4, 6.0, 1.3])
    cams = [_cam([x, 0, 1.5], 0.02 * i) for i, x in enumerate(np.linspace(-1, 1, 12))]
    uv = np.array([tm.project(X, M, f, cx, cy)[0][0] for M in cams])
    Xr = tm.triangulate(cams, uv, f, cx, cy)
    assert np.allclose(X, Xr, atol=1e-6)
    assert max(tm.reproj_errors(Xr, cams, uv, f, cx, cy)) < 1e-6


def test_distortion_roundtrip():
    k = (-0.08, 0.01, 0.0)
    xn = np.array([[0.3, -0.2], [0.05, 0.4]])
    assert np.allclose(tm.undistort(tm.distort(xn, k), k), xn, atol=1e-9)
    f, cx, cy = 1200.0, 960, 540
    X = np.array([-1.0, 5.0, 0.4])
    cams = [_cam([x, 0, 1], 0) for x in np.linspace(-1, 1, 8)]
    uv = np.array([tm.project(X, M, f, cx, cy, k)[0][0] for M in cams])
    assert np.allclose(tm.triangulate(cams, uv, f, cx, cy, k), X, atol=1e-6)


def test_holdout_catches_a_bad_solve():
    """Cameras that are subtly wrong still fit their own tracks after BA, but a
    point triangulated from them reprojects worse than one from the true path."""
    f, cx, cy = 1500.0, 960, 540
    X = np.array([1.0, 8.0, 2.0])
    true = [_cam([x, 0, 1.5], 0) for x in np.linspace(-1, 1, 10)]
    uv = np.array([tm.project(X, M, f, cx, cy)[0][0] for M in true])
    wrong = [_cam([x * 1.3, 0.2 * x * x, 1.5], 0.01 * x) for x in np.linspace(-1, 1, 10)]
    e_true = np.median(tm.reproj_errors(tm.triangulate(true, uv, f, cx, cy), true, uv, f, cx, cy))
    e_wrong = np.median(tm.reproj_errors(tm.triangulate(wrong, uv, f, cx, cy), wrong, uv, f, cx, cy))
    assert e_true < 1e-6 and e_wrong > 0.5


def test_spikes_and_coverage():
    series = {i: 0.2 for i in range(1, 50)}
    series[30] = 2.5
    assert tm.spikes(series) == [30]
    cov = tm.coverage({1: [(0.1, 0.1), (0.5, 0.5), (0.9, 0.9)], 2: [(0.1, 0.1), (0.12, 0.15)]})
    assert cov == {1: 3, 2: 1}
