# Studio viewer and event log

The viewer shows what the engine did, live, without any AI calls. It is read-only.

## Start it (on the machine with the projects, usually the user's Mac)

```
python3 scripts/vfx.py studio --root PROJECTS_FOLDER --open
```

It prints a link with a one-time token and opens it. Keep the Terminal window open; Ctrl+C stops it. It listens on 127.0.0.1 only.

## What it shows

- Activity: engine operations (PASS, FAIL, UNKNOWN, running, interrupted) and notes, newest first. Click for command, outputs, errors and script changes.
- Unrecorded changes: files that changed after logging began with no engine event to explain them, such as edits made directly in Blender. Treat these as unverified.
- Review images: the shot's `_review/` folder and images named by events.
- Machines: preflight reports, one per machine (`_studio/preflight/<machine>.json`).

## Agent rules

- Every engine command that changes a shot logs `op.start` and `op.end` itself. Do not write op events by hand.
- Before a step, log one line: `vfx.py event note SHOT "Render frames 40-60 to check the glass" --source cowork`.
- Before running a script through Blender MCP: `vfx.py snapshot SHOT path/to/script.py`. Only small UTF-8 text is stored; diffs are computed when viewed.
- An op with no end event is interrupted, not done. `vfx.py event reconcile SHOT` records that on the machine that ran it.
- Run `vfx.py preflight --root PROJECTS` on each machine that does work. A Cowork VM report says NOT_APPLICABLE for Blender: that is expected, it cannot run the Mac's Blender.
