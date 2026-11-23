---
name: blender-vfx
description: Plan, build and review realistic VFX shots in Blender, from CG put into live action footage to full CG shots. Interviews the user about their camera, computer and shot, asks for approval before slow or risky steps, and loads only the guide for the current stage to save tokens. Use for camera tracking, CG integration, simulations, lighting to match a plate, render passes, compositing, or any hyper-realistic Blender shot.
---

# Blender VFX

A working method for realistic shots in Blender, built from how working VFX artists put CG into real footage. Blender does the tracking, 3D, simulation, rendering and integration compositing. A grading app (DaVinci Resolve or similar) does the edit, grade and sound.

## Rule zero: ask, then build

Never guess a shot. Before any work:

1. **Lessons.** If `lessons.md` exists in the project, read it first. It holds what worked and failed on this user's earlier shots.
2. **Setup profile.** Look for `vfx-profile.md` in the project folder (or saved memory). If it is missing, run the setup interview in `references/00-setup-interview.md` once and save the answers there. Never ask those questions again; read the profile.
3. **Shot brief.** For every new shot, run the shot interview in `references/01-shot-brief.md`. Turn the answers into a written brief with acceptance checks.
4. **Plan approval.** Show the brief, the plan (which stages, which tools, rough time) and the checks. Wait for a yes.

Ask in rounds of at most 4 questions, each with options to pick from. Use a question tool if one exists.

## Approval gates (always stop and ask)

- Before any render or simulation bake estimated over 10 minutes (or the user's own limit in the profile). State the estimate, settings, frame range and output path.
- Before the final render: show a contact sheet of preview frames and the checklist status.
- Before overwriting or deleting anything the user made: their .blend, footage, renders, assets, preferences. Save a new version instead (`shot010_v003.blend`).
- Before downloading paid assets, installing add-ons, or changing app-wide settings.
- When something fails twice the same way (track will not solve, out of memory, crash), stop, explain, offer options.
- When the brief asks for something the hardware or the footage cannot deliver, say so before starting, with the closest workable option.

## Stage map: load only what you need

| Stage | Load |
| --- | --- |
| First run | `references/00-setup-interview.md` |
| New shot | `references/01-shot-brief.md` |
| Before or during a shoot | `references/02-shooting-the-plate.md` |
| Log footage, colour spaces, round trips | `references/03-color-pipeline.md` |
| Camera tracking, set rebuild | `references/04-tracking.md` |
| Models, materials, digital doubles | `references/05-assets-materials.md` |
| Animation, mocap | `references/06-animation.md` |
| Smoke, fire, water, destruction, cloth | `references/07-simulation.md` |
| Lighting, render passes, render settings | `references/08-lighting-rendering.md` |
| Compositing in Blender | `references/09-compositing.md` |
| Grade, sound, 16:9 and 9:16, festival masters, asset licences | `references/10-finishing-delivery.md` |
| Speed and memory for the user's machines | `references/11-hardware.md` |
| Review before showing anything | `references/12-review-checklist.md` |
| Controlling DaVinci Resolve | `references/13-resolve-automation.md` |
| Slow renders, faster settings, computer tuning | `references/14-render-speed.md` |
| A common effect (saber, explosion, creature, sky swap, removal...) | `recipes/README.md`, then one recipe |
| Learning links, where a method came from | `references/video-index.md` |
| Folder layout, cleaning up a messy project | `references/15-project-structure.md` |

Read one stage file, do the work, move on. Do not preload the whole folder.

## Rules that never bend

- Real meters. A 1.75 m human reference stays in the scene until the final render. Apply scale before modifiers and physics.
- Match the real camera: same sensor width, focal length, frame rate and shutter as the plate.
- Real scanned PBR materials. Base colour is sRGB, every other map is Non-Color. Roughness is never one flat value. Bevel hard edges.
- Every light has a source you can point to in the plate. One dominant key.
- Simulate what physics should drive. Animate what acts. Use stock elements for anything huge.
- Same frame, same image: fixed seeds, frame-driven time, every simulation baked.
- Render multilayer EXR sequences, never straight to a video file.
- Fix one thing at a time and re-render only the affected frames.
- Open and look at a render before saying anything about it. Never report done until `references/12-review-checklist.md` passes.
- Keep an asset licence log from the first download.

## Files: keep the project clean

Follow the layout in `references/15-project-structure.md` (numbered folders: `00_brief` to `09_deliver`, plus `scripts`, `logs`, `_review`, `_tmp`, `_archive`). In short:

- Nothing in the project root except `README.md`. Pick the folder before writing a file.
- One script per pipeline step, edited in place (`03_build_scene.py`), never copied as `_v2` or `_final`. Versions belong to .blend files and render folders.
- Temp and converted files go to `_tmp/` and are deleted once the step is verified. Debug images go to `_review/` and replace the previous check.
- Never move or rename files while a render, bake or scheduled job uses them.
- End of session: run `scripts/tidy_project.py` (dry run), clear `_tmp/`, update `README.md`, report new files and disk used in 2 or 3 lines. Deleting anything else needs the user's yes.

## Scripts (in `scripts/`, run inside Blender unless noted)

- `probe_scene.py`: compact JSON summary of the scene. Use instead of listing objects.
- `render_doctor.py`: read-only check of what makes a render slow, ranked, with quality risk per fix.
- `setup_shot.py`: folders, units, fps, camera sensor and focal length, colour view, Cycles defaults per hardware tier, EXR output and passes, versioned save.
- `contact_sheet.py`: renders chosen frames cheaply and tiles them into one image, restoring all settings.
- `verify_output.py` (plain Python with ffmpeg): frame count, gaps, black frames, flicker spikes.
- `tidy_project.py` (plain Python): finds root clutter, temp files, script copies and byte-identical duplicates; deletes only with explicit flags.

## Learning loop

After each finished shot, add 1 to 3 lines to `lessons.md` (template in `templates/`): settings that worked, mistakes to avoid, preferences the user showed. This is how the skill gets better for each user without retraining.

## Working with Blender through MCP or scripts

- Confirm the target first: Blender version, open file, scene name. One writer per scene.
- Live MCP edits only in the scene the user asked about. Long renders and batch jobs run headless (`blender -b file.blend -P script.py`) on a saved copy.
- Restore any render settings a tool changed for a preview.
- Measure evaluated geometry (after modifiers), never raw mesh data.

## Token budget

- Load one stage file at a time (table above). Never re-read a file already in context.
- Keep state in `shot-log.md` (template in `templates/`). Update it after each stage in 3 to 5 lines; read it instead of re-checking the whole scene.
- Inspect scenes with `scripts/probe_scene.py`, which returns compact JSON. Never dump full object or node lists.
- Batch related Blender edits into one script call that returns only counts and errors.
- Big results (object lists, logs, render stats): aggregate inside Blender or write to a temp JSON file and return its path. Page anything long.
- Look at images only at checkpoints. Preview renders at 25 to 50 percent resolution with low samples. Prefer one contact sheet over many single frames.
- Write long explanations to files; keep chat replies short.
