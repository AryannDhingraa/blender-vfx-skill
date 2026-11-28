# Studio viewer and event log

The viewer shows what the engine did, live, without any AI calls. It is read-only.

## Start it (on the machine with the projects, usually the user's Mac)

```
python3 scripts/vfx.py studio --root PROJECTS_FOLDER --open
```

It prints a link with a one-time token and opens it. Keep the Terminal window open; Ctrl+C stops it. It listens on 127.0.0.1 only.

## What it shows

- Two display modes over the same records: Filmmaker (plain words) and VFX Artist (commands, results, code). Neither changes the shot.
- Overview: stage, what is running, latest image, readiness per machine, problems, learning and research settings, machine dials. Live Blender view and approvals are labelled as not available yet.
- Activity: engine records and Claude's notes, kept visibly apart. Clicking one opens Explain this change: what happened, why, what it touches, effect on the picture, how to do it by hand, then technical details.
- Images, Machine (CPU, GPU busy, unified memory, pressure, swap, free storage, thermal state, Blender and ffmpeg processes, the viewer's own cost), Outside changes, Alerts.
- Links open a screen directly: `#view=activity&mode=vfx-artist&shot=SHOT&open=snapshot`.

## How it stays reliable

- Each machine writes its own log (`state/events.<machine>.jsonl`), so the Mac and the Cowork VM never append to the same file; processes on one machine take an OS lock. The shot record (`state.json`) still has one writer machine at a time: run engine commands for a shot on one machine.
- Every stream message has a sequence number. A gap, a reconnect or a 30 s timer makes the page reload the full state, so a missed message is never permanent.
- New shot folders are found within about 10 s.
- Scripts that look like they hold a password, token or key are not stored (hash only), and such values are redacted from event text.
- Machine readings use only unprivileged system calls and commands, every 10 s while a page is open and every 60 s otherwise; their cost is shown on the Machine page.

## Agent rules

- Every engine command that changes a shot logs `op.start` and `op.end` itself. Do not write op events by hand.
- Before a step, log one line: `vfx.py event note SHOT "Render frames 40-60 to check the glass" --source cowork`.
- Give engine commands a plain title, purpose and component when they matter to the user: `vfx.py run ... --title "Render the glass test frames" --purpose "check the refraction after the IOR change" --component "Iris glass material"`. Never invent a purpose after the fact.
- Before running a script through Blender MCP: `vfx.py snapshot SHOT path/to/script.py`. Only small UTF-8 text is stored; diffs are computed when viewed.
- An op with no end event is interrupted, not done. `vfx.py event reconcile SHOT` records that on the machine that ran it.
- Run `vfx.py preflight --root PROJECTS` on each machine that does work. A Cowork VM report says NOT_APPLICABLE for Blender: that is expected, it cannot run the Mac's Blender.
