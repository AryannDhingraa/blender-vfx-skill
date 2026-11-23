# Project structure and file hygiene

A person should open the project folder and understand it in 10 seconds. The agent follows the same layout and never scatters files.

## Layout

```
MyFilm/
  README.md          5 lines: what this is, current status, where the latest output is
  00_brief/          vfx-profile.md, shot-log.md, lessons.md, asset-licenses.md, reference images
  01_source/         original camera clips. Read-only. Never edited, renamed or converted in place
  02_plates/SHOT/    prepared plate sequences, one format per shot (plate_0001.png ...)
  03_track/SHOT/     tracking data: markers, camera solve
  04_assets/         models, textures, HDRIs shared by all shots
  05_blend/SHOT/     SHOT_v003.blend (versioned scene files)
  06_cache/SHOT/     simulation bakes. Rebuildable, safe to clear after the final
  07_renders/SHOT/v003/<layer>/0001.exr
  08_comp/SHOT/v003/0001.png
  09_deliver/        finished videos: SHOT_v003.mp4, masters, vertical cuts
  scripts/           one script per pipeline step (see below)
  logs/              one log per render layer, replaced on each run
  _review/           contact sheets and debug frames for the current check only
  _tmp/              scratch. Emptied at the end of every session
  _archive/          superseded versions, moved here, never deleted without asking
```

Single-shot projects skip the `SHOT/` level.

## Rules for the agent

1. **Nothing in the root** except `README.md`. Decide the folder before writing any file.
2. **Scripts are edited, not copied.** One file per step, numbered in run order: `01_prep_plate.py`, `02_track.py`, `03_build_scene.py`, `04_render.py`, `05_comp.py`, `06_finish.sh`. No `build_v2.py`, `build_final.py`, `build_final2.py`. Put the project under git (`git init`, ignore everything except `scripts/`, `00_brief/` and `README.md`) so old script versions live in history, not as files.
3. **Versions belong to scenes and outputs**, not scripts: `05_blend/SHOT/SHOT_v004.blend`, `07_renders/SHOT/v004/`. Bump the version only when the result changes in a way the user would want to compare.
4. **Temporary files go to `_tmp/`** and are deleted as soon as the step that needed them is verified. Never leave a converted copy next to the original (no `plate_tmp_0001.png` beside `plate_0001.png`).
5. **Debug images go to `_review/`**, overwrite the previous check, and get cleared when the user approves. One contact sheet per check, not loose frames.
6. **One log per render layer** in `logs/`, replaced on each run. Trim logs to the last run.
7. **Blender auto-backups**: set Preferences, Save and Load, Save Versions to 0 for VFX projects, because versions are saved by hand. Ask before changing it; it is an app-wide setting.
8. **Superseded experiments** (old test scenes, old renders) move to `_archive/` with a one-line note in `README.md`. Deleting anything outside `_tmp/` needs the user's yes.
9. **Names**: lowercase, no spaces, `shot_layer_v###`, frames padded to 4 digits (`0001`).
10. **End of every session**: run `scripts/tidy_project.py` (dry run), clear `_tmp/`, update `README.md`, and report new files and disk used in 2 or 3 lines.
11. **Never move or rename files while a render, bake or scheduled job is using them.** Paths in scripts would break. Tidy after the job finishes.

## Why it saves tokens

The agent reads `README.md` and `00_brief/shot-log.md` to know where things are, instead of listing hundreds of frames. Frame folders are never listed in full; check them with counts (`verify_output.py`).
