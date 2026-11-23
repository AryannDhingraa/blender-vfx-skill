# Shot interview and brief

Run this for every new shot. Ask in rounds of up to 4, with options. Use the profile so you never re-ask gear questions.

## Questions

Round 1: the idea
1. What happens in the shot, in one or two sentences?
2. Reference: a film shot, a video, or images it should look like. Ask for links or files.
3. Is there footage already (plate shot), or are we planning the shoot?
4. Length in seconds and number of shots in the sequence.

Round 2: the effect
1. What is CG: a character, a vehicle, a prop, destruction, fire, smoke, water, weather, environment, set extension, removal?
2. Does the CG touch the real world (contact, shadows, splashes, dust) or the actor (held, hit, lit by it)?
3. Camera: locked off, slow move, handheld, drone, fast action?
4. Day, night, or day-for-night? Indoors or outdoors?

Round 3: limits
1. Deadline.
2. Quality target: test or previz, social post, polished YouTube, festival.
3. Which deliveries: 16:9, 9:16, both.
4. Anything that must not change (the actor's performance, the grade, an existing edit).

## Choose the composite strategy

Pick the lightest one that works and say why:

| Strategy | Use when |
| --- | --- |
| 2D | Locked or near-locked camera, flat element (saber blade, muzzle flash, screen replacement, sky swap) |
| 2.5D | Small camera move; cards or projected stills in 3D space (matte painting, set extension far away) |
| 3D matchmove | Camera moves through space and CG must stick to the ground, cast shadows or be lit by the plate |
| Full CG | Nothing real would survive the effect, or the camera does something impossible |

## Write the brief

Save to `shot-log.md` (template in `templates/`):

- Shot ID, one-line description, reference links.
- Strategy and the stage list you will run.
- Assets needed and where they come from (with licence).
- Estimated time per stage on this user's hardware.
- Acceptance checks with numbers where possible, for example:
  - Camera solve error under 0.3 px.
  - No visible sliding at the contact points at full resolution.
  - CG black level within the plate's black level.
  - Grain on the CG matches the plate at 100 percent zoom.
  - Reads correctly in 9:16 crop (if delivering vertical).
- Approval gates for this shot (renders over the user's time limit, purchases).

Show the brief in under 15 lines and ask for approval before building.
