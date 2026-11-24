# vfx_engine

The tools the agent runs, kept apart from the skill's instructions. The skill decides what to do; these scripts do it and report back in one JSON line, so results are measured, not assumed.

| Tool | Status | What it does |
| --- | --- | --- |
| `analyse_footage.py` | Working | Reads a plate before tracking: sharpness, exposure, clipped highlights, and whether the camera is locked, rotating or moving with parallax. Recommends the solve type |
| `run_job.py` | Working | Runs Blender headless with a timeout and a log, then checks the outputs exist, are new and match the expected count |

Needs Python 3.10+, `numpy` and `opencv-python` (or `opencv-python-headless`).

## Roadmap

1. **Tracking**: compare Blender's solve with an optional COLMAP solve on the same shot, holdout-track checks, lens calibration from a checkerboard.
2. **Execution**: checkpoints and automatic retry for safe steps, a job history file.
3. **Masks and depth**: optional AI masks for actors and foreground, optional depth maps, each behind a hardware and licence check.
4. **Visual review**: before and after contact sheets per revision, temporal flicker checks.
5. **Benchmark**: a fixed set of test shots (`docs/test-shots.md`) that every change must pass.
