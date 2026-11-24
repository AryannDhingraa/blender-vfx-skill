# Changelog

## 2.0.0 (2026-11-24)
- One engine, `scripts/vfx.py` plus the `vfxlib` package, replaces shot_state.py, verify_output.py, tidy_project.py and the separate vfx_engine folder. Old commands map to `vfx.py state`, `verify`, `tidy`, `analyse`, `run`.
- Footage: the camera move is only named with enough evidence (frames, features, consistent pairs); otherwise "unknown" with reasons. Decided from homography residuals, so results no longer change between OpenCV versions.
- Tracking: track_report.py adds per-frame reprojection error and spike frames, coverage on every frame, automated holdout tracks (`--prepare-holdout`), a trust level, and a self-check against Blender's own errors.
- State: schema validation, OS file locks, checksummed history, recovery that also refreshes the backup, and dependency-aware results: when an input changes, everything built from it is reported stale.
- Jobs: per-job manifests, Blender's Python errors return an exit code, structural checks of PNG, JPEG, EXR and TIFF frames, detection of interrupted jobs, resume that re-renders only missing, corrupt or stale frames, a 3-attempt limit, and one writer per output folder.
- Assets: Poly Haven and ambientCG search ranked for the machine, thumbnail contact sheet, download only with `--approved`, checksums, licence log; import_asset.py; procedural_asset.py as the fallback.
- Destruction: build_proxy.py (RANSAC planes from tracked points, plate projection baked to UVs) and destruction.py (partial fracture at the impact only).
- SKILL.md is 26 percent smaller. Tests: 54 (real Blender 4.2, 5.1, 5.3), CI on Linux, macOS and Windows.

## 1.5.0 (2026-11-24)
- Filmmaker and VFX Artist modes (17-modes-and-learning.md). Learning off by default, on request only.
- Resource manager (18-resource-manager.md): tool-call checks, reuse of recorded results, budget levels, free only on by default.
- shot_state.py: small per-shot state with backup, history and crash recovery.
- Tracking: solve error is now one diagnostic among several, not a pass or fail line.
- Setup interview: "I don't know" allowed, hardware detected where possible, mode picked from experience.
- README: Working, Experimental and Planned labels; what is checked automatically and what needs a human.
- Shot form: skill version, agent, result, permission scope, third-party rights. SHOWCASE.md split into featured, experimental and failed.
- Evals: 5 new cases (13 total).

## 1.4.0 (2026-11-24)
- vfx_engine: analyse_footage.py (shot type, blur, exposure, recommended solve) and run_job.py (headless Blender with timeout, log and verified outputs).
- docs: 20-shot benchmark list, rendering beyond one machine.
- Community: shot submission form, SHOWCASE.md.

## 1.3.0 (2026-11-24)
- track_report.py: solve trust report (median and 95th percentile error, tracks per frame, image spread, lifespans, flags).
- Tracking guide: shot classification, holdout and forward-backward checks, lens calibration.
- Review: technical, visual and human gates; compare every revision with the previous one.
- Execution rules: verify outputs after every job, checkpoints before risky steps.
- Optional engines guide (COLMAP, OpenCV, AI point tracking, AI masks, depth) with licence and hardware notes.
- New README with breakdown and before/after media.

## 1.2.0 (2026-11-24)
- Standard project layout and file hygiene rules; setup_shot.py creates it, contact_sheet.py writes to _review/ and replaces the old sheet.
- tidy_project.py: finds root clutter, temp files, copied scripts and byte-identical duplicates; deletes only with explicit flags.

## 1.1.0 (2026-11-24)
- Render doctor script and render speed guide (Blender settings and computer tuning for macOS, Windows, Linux).
- DaVinci Resolve automation guide (Studio, Free 21.1+ Lua bridge, Free 21.0).
- Ten effect recipes, learning links, lessons loop, shot setup and contact sheet scripts, eval cases.

## 1.0.0 (2026-11-24)
- First release: setup and shot interviews, approval gates, 13 stage guides, hardware tiers, colour round trip, scene probe and output verification scripts.
