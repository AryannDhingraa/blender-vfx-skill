# Changelog

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
