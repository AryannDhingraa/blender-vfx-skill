# Resource manager

Use the cheapest method that reaches the quality the shot needs. Four costs are counted: AI tokens, tool and script calls, the computer (time, memory, disk, heat), and outside services (downloads, cloud, paid APIs).

## Before every tool call

1. Is it needed for this step?
2. Is the answer already known? `vfx.py status SHOT_DIR` shows state, stale results and jobs in one call.
3. Can a recorded result be reused? `vfx.py state check SHOT_DIR NAME` says whether its files, inputs and settings are unchanged.
4. Is there a cheaper way that is good enough?
5. Will the call change the result?

If not, skip it. Never repeat a successful call without a reason. Never retry a failed call the same way: change something or stop and ask (the "fails twice" gate).

## Which tool when

| Tool | Use when |
| --- | --- |
| `probe_scene.py` | A .blend exists and you need its state. Once per session unless the scene changed |
| `vfx.py analyse --state` | New plate, or the plate changed. It records the result itself |
| `track_report.py` | The shot needs a camera solve, after each solve |
| `render_doctor.py` | A render estimate is over the user's limit, or a render is slower than expected |
| `contact_sheet.py` | Before a gate, or to compare revisions. Not after every edit |
| `vfx.py run`, `resume` | Every headless render or bake; resume re-renders only bad frames |
| `vfx.py verify` | After a video export or to check frames without a job |
| `vfx.py tidy` | End of session, or when the user asks |
| `vfx.py assets search` | Only when no asset in `04_assets/` fits; one search, one sheet |

Pick the smallest workflow for the shot. A still object on a locked-off shot needs a patch, not a camera solve and an AI mask. A person crossing a moving shot needs the full chain.

## Budget levels (saved in the profile, can be set per shot)

| Level | What changes |
| --- | --- |
| Economy | Fewest calls, previews at 25 percent and low samples, one contact sheet per gate, no optional engines unless asked |
| Balanced (default) | Previews at 50 percent, optional engines only when a cheaper check has failed |
| Quality first | Extra analysis passes, more review frames, comparison renders when they would change a decision |

The level never lowers the final render quality the user approved. It only changes how much work goes into getting there.

## Free only (on by default)

With free only on, never use or suggest: paid assets, paid add-ons, paid APIs, cloud GPUs, render farms that charge, or subscriptions. Free and open tools, CC0 assets, the user's own machines, free community farms and free notebook tiers are fine, after the usual approval for downloads and uploads.

Whatever the setting, never spend money or start a paid service without the user's explicit yes in chat.

## Reading files

- Load one stage guide at a time, from the stage map. Never preload the folder.
- Read the shot state summary, not the whole history. `history.jsonl` is only for `state recover`.
- Record outputs with `vfx.py state record NAME FILES --deps INPUTS`; when an input changes, everything built from it shows as stale, so redo only that chain.
- Logs stay on disk. Bring in only the error lines (`vfx.py run` already returns them).
- Never re-read a file that is already in context and unchanged.

## Measuring

Agents do not expose exact token counts for every step. Track what can be seen: number of tool calls, scripts run, files read and their size. At the end of a shot, report them in one line in the shot log. Do not invent token figures.
