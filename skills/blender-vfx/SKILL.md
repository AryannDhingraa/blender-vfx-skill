---
name: blender-vfx
description: Plan, build and review realistic VFX shots in Blender, from CG put into live action footage to full CG shots. Interviews the user about their camera, computer and shot, asks for approval before slow or risky steps, and loads only the guide for the current stage to save tokens. Use for camera tracking, CG integration, destruction, asset finding, simulations, lighting to match a plate, render passes, compositing, or any hyper-realistic Blender shot.
---

# Blender VFX

A working method for realistic shots in Blender. Blender does tracking, 3D, simulation, rendering and integration compositing; a grading app (DaVinci Resolve or similar) does the edit, grade and sound. Tools live in `scripts/`: `vfx.py` (plain Python) and Blender scripts.

## Rule zero: ask, then build

1. Run `python3 scripts/vfx.py status SHOT_DIR` (state, stale results, unfinished jobs). Read `lessons.md` if it exists.
2. No `vfx-profile.md`: run `references/00-setup-interview.md` once and save it. Never re-ask; read the profile.
3. New shot: `references/01-shot-brief.md`, then `vfx.py state init SHOT_DIR`.
4. Show the brief, plan (stages, tools, rough time) and checks. Wait for a yes.

Ask in rounds of at most 4 questions, each with options. Use a question tool if one exists.

## Modes, learning, resources

- **Mode:** Filmmaker (default) uses film words and one plan; VFX Artist uses terms, options and trade-offs. Same checks and gates. `references/17-modes-and-learning.md`.
- **Learning is off** until the user asks ("teach me this", "explain briefly", "quiz me"; "back to work" stops). Off never skips checks or gates.
- **Resources:** before any tool call ask: needed? already known? reusable? cheaper way? Budgets Economy, Balanced (default), Quality first. Free only is on by default; never spend money silently. `references/18-resource-manager.md`.

## Approval gates (always stop and ask)

- Any render, bake or simulation estimated over 10 minutes (or the profile's limit): state estimate, settings, frames, output path.
- The final render: show a contact sheet and the checklist status first.
- Overwriting or deleting anything the user made. Save a new version instead (`shot010_v003.blend`).
- Downloading assets (show the options sheet first), installing add-ons, changing app-wide settings, anything paid.
- The same failure twice (track will not solve, out of memory, crash): stop, explain, offer options. `vfx.py resume` refuses after 3 attempts.
- When the brief needs more than the hardware or footage can give: say so first, with the closest workable option.

## Stage map: load only what you need

| Stage | Load |
| --- | --- |
| First run / new shot | `references/00-setup-interview.md` / `references/01-shot-brief.md` |
| Shooting the plate | `references/02-shooting-the-plate.md` |
| Log footage, colour round trips | `references/03-color-pipeline.md` |
| Tracking, solve trust, set rebuild | `references/04-tracking.md` |
| Finding, approving and importing assets; materials | `references/05-assets-materials.md` |
| Animation | `references/06-animation.md` |
| Simulation, destruction | `references/07-simulation.md`, `recipes/split-and-destruction.md` |
| Lighting, passes, render settings | `references/08-lighting-rendering.md` |
| Compositing | `references/09-compositing.md` |
| Grade, sound, delivery, licences | `references/10-finishing-delivery.md` |
| Hardware, slow renders | `references/11-hardware.md`, `references/14-render-speed.md` |
| Review before showing anything | `references/12-review-checklist.md` |
| DaVinci Resolve control | `references/13-resolve-automation.md` |
| Folder layout, cleanup | `references/15-project-structure.md` |
| Hard footage: COLMAP, AI masks, depth | `references/16-optional-engines.md` |
| Common effects | `recipes/README.md`, then one recipe |
| Where a method came from | `references/video-index.md` |

Read one stage file, do the work, move on.

## Tools

`vfx.py` (run `python3 scripts/vfx.py -h` once if unsure of a flag):
- `status`, `state init|set|done|reopen|record|check|invalidate|recover`: shot state under 4 KB, locked, recoverable. Record outputs with `--deps`; when an input changes, everything built from it shows as stale.
- `analyse PLATE --state SHOT_DIR`: camera move (locked, rotation, parallax or unknown with reasons), blur, exposure, solve type. Never guess a move it calls unknown.
- `run JOB --state SHOT_DIR --blend F --frames 1-100 --pattern OUT/####.exr`, `resume JOB`, `job JOB`: headless Blender with timeout, log and verified frames; resume re-renders only missing, corrupt or stale frames.
- `verify TARGET`: frames or video; missing, truncated, black, flicker.
- `assets search|download`, `tidy PROJECT`, `doctor`, `package OUT.zip`.

Blender scripts (`blender -b file.blend -P script.py -- args`, or exec through MCP): `probe_scene.py` (compact scene JSON), `setup_shot.py` (folders, camera, colour, render defaults, versioned save), `render_doctor.py` (what makes a render slow), `contact_sheet.py` (cheap preview sheet), `track_report.py` (solve trust: per-frame error, coverage over time, holdout tracks, self-check), `build_proxy.py` (walls and floors from tracked points with plate projection), `destruction.py` (partial fracture at the impact only), `import_asset.py`, `procedural_asset.py` (fallback assets with preview).

Report tool JSON, not impressions. A tool saying success is not proof; check its numbers.

## Rules that never bend

- Real meters; a 1.75 m reference stays until the final. Apply scale before modifiers and physics.
- Match the real camera: sensor width, focal length, frame rate, shutter.
- Scanned PBR: base colour sRGB, other maps Non-Color, no flat roughness, bevelled edges.
- Every light has a source in the plate; one dominant key.
- Simulate what physics drives, animate what acts, stock elements for anything huge.
- Fixed seeds, frame-driven time, every simulation baked.
- Multilayer EXR sequences, never straight to video. Fix one thing at a time; re-render only affected frames.
- Look at a render before describing it. Never report done until `references/12-review-checklist.md` passes.
- Log every asset licence from the first download.

## Files

Layout in `references/15-project-structure.md`. Nothing in the project root but `README.md`. One script per step, edited in place, never `_v2` copies. Temp files in `_tmp/`, debug images in `_review/` replacing the last check. Never move files a job is using. End of session: `vfx.py tidy` (report), clear `_tmp/`, update `README.md`, report new files and disk used in 2 or 3 lines. Deleting anything else needs a yes.

## Blender through MCP or scripts

- Confirm Blender version, open file and scene first. One writer per scene.
- Live MCP edits only in the scene asked about. Long renders and batches run headless through `vfx.py run` on a saved copy.
- Restore render settings a preview changed. Measure evaluated geometry.
- Prefer `bpy.data` over operators; use `bpy.context.temp_override()` when an operator needs context. Clip Editor operators read `space.clip_user.frame_current`, not `scene.frame_current`: set both.
- Never start long jobs with `&` or nohup from an agent shell; it dies when the call ends. Use `vfx.py run`/`resume`, or a detached launcher (new session, log, pid and exit files) with checkpoints.
- Blender 5.1: a render saved as multilayer EXR may hold only Combined; write passes through a compositor File Output node, or put depth haze in the shaders (Camera Data > View Distance). Set `media_type = 'MULTI_LAYER_IMAGE'` before the file format.
- Retargeting Mixamo onto another rig: compute local bases with explicit parent maths (never set pose bones and update the depsgraph inside the bake loop) and align rest poses joint to joint, not by bone tails.
- Save a new .blend version before risky steps.

## Token budget

- One stage file at a time; never re-read a file already in context.
- `vfx.py status` instead of re-inspecting; `shot-log.md` is human notes, read only its last entry.
- Batch Blender edits into one call that returns counts and errors. Write big results to a file and return its path.
- Images only at checkpoints: previews at 25 to 50 percent, one contact sheet instead of many frames.
- Keep chat replies short; long explanations go to a file.

## Learning loop

After each finished shot, add 1 to 3 lines to `lessons.md` (template in `templates/`): what worked, what to avoid, the user's preferences.
