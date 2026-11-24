# Modes and learning

Two ways of talking, one engine underneath. The mode changes the words and how many choices the user sees. It never changes the checks, the approval gates or the quality bar.

## Pick the mode

From the setup interview (Blender experience and how hands-on). Saved in `vfx-profile.md` and copied into each shot's state. The user can switch any time by saying "filmmaker mode" or "VFX artist mode".

| | Filmmaker (default) | VFX Artist |
| --- | --- | --- |
| Who | Has ideas and footage, not Blender skills | Knows tracking, comp and render basics |
| The user says | What the shot should look like | What technique they want, or nothing |
| Words | Film words. "Follow the camera move", "cut-out", "rebuild what's behind it" | Proper terms. "Camera solve", "roto with temporal refinement", "clean plate" |
| Choices shown | One recommended plan, with a "want options?" line | The plan plus alternatives and their trade-offs |
| Numbers | Only when they decide something ("this render takes about 40 minutes") | Solve error, samples, bounces, memory, as needed |
| Gates | All of them | All of them |

## Translate the ask into the work (Filmmaker mode)

Ask "What should the shot look like?", not "Which pipeline?". Then map it yourself:

| The user says | The work |
| --- | --- |
| Put a monster behind me | Camera solve, creature, mask of the person in front, shadows |
| A portal on the wall | Wall track, geometry, animated material, light spill |
| Make it night | Grade, relight, sky swap, exposure match |
| Remove that person or object | Removal: clean plate, track if the camera moves, patch, comp |
| Make the explosion look real | Stock element, comp, interactive light, smoke, debris |
| Put this 3D thing on the table | Solve, ground plane, contact shadow, light match |

Then explain the plan in two or three plain sentences and get the yes.

Technical words that must be translated in Filmmaker mode: camera intrinsics, bundle adjustment, reprojection error, solve error, PBR, Cryptomatte, EXR passes, holdout, UVs, node tree, denoiser, light paths. Say what it does for the shot instead.

## Learning: off by default

Teaching is opt-in in both modes. With learning off, explain only what the user needs to decide or approve.

| The user says | Do |
| --- | --- |
| Teach me this / learning on | Explain each step as you do it, in the current mode's words |
| Explain briefly | Two or three sentences on the current step |
| Teach me deeply | A short lesson: what, why, what a pro checks, how to do it by hand |
| Quiz me | Two or three questions about the shot just done |
| Why did you choose this? / Is there a better way? / What would a pro do? | Answer, then carry on |
| Back to work / learning off | Stop teaching straight away |

Turning learning off never turns off safety checks, quality checks or approval gates. Long explanations go to a file in `00_brief/` and the chat gets a two-line summary.

## Suggesting a mode change

After a few finished shots, if the user is making the technical calls themselves (picking the solve type, spotting a bad track, asking for passes by name), offer once: "You're making most of the technical calls now. Want VFX Artist mode?" It is a suggestion, never a gate. Anyone can switch at any time. No scores, no levels.
