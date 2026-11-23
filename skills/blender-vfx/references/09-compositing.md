# Compositing in Blender

Blender's compositor reads its own EXR passes directly and can be driven by script, so integration compositing happens here. Heavy roto and paint can go to the grading app's compositor (Fusion in Resolve) if the user prefers.

Work in this order. Check each step at 100 percent zoom and in motion.

1. **Plate in**, in the colour space chosen in `03-color-pipeline.md`. Undistort if the solve used distortion.
2. **CG over plate** (Alpha Over). Multiply in the shadow catcher pass.
3. **Match levels.** CG black level, white point, saturation and shadow colour to the plate. Sample a real shadow and a CG shadow; they should match. Lift CG blacks if they are deeper than anything in the plate.
4. **Grade passes separately.** Fire warmer with glow, smoke brighter with noise-driven colour variation (real smoke is never one colour), emission with glare.
5. **Match the camera.** Defocus, motion blur (Vector pass), lens distortion back on, chromatic aberration at the edges if the lens shows it.
6. **Roto real foreground** back over the CG (Mask editor): branches, grass, hands, the actor.
7. **Atmosphere in three layers:** behind the CG, blended with it, in front of it. Use the Mist or Z pass to fade fog with distance.
8. **Stock elements** to break up clean CG: dust hits, debris, sparks, rain (far rain behind the subject, near rain in front).
9. **Interactive light on the plate:** flashes, fire glow, a glowing prop lighting the actor. Lightning: drive brightness of plate, CG and fog from the sky's brightness per frame.
10. **Lens character:** glow on highlights, a little lens dirt, re-add any lens flare the CG covered.
11. **Camera shake** on impacts, matched to the shot's existing motion.
12. **Grain last.** Match the plate's grain size and strength over the whole frame, CG included.
13. **Paint out** rigs, gear and stand-ins (clean plate first, AI fill as a tool if the user allows it).

Output: EXR sequence (or ProRes 4444) back to the grading app, in the same colour space the plate came in.

## Day for night

Shoot in daylight. Replace the sky with a night sky, darken the land heavily (bright peaks most), add a motivated back light to the subject, grade cool and dark, keep some detail in the shadows.

## Common giveaways

- CG blacks deeper than the plate.
- CG sharper than the plate (no defocus, no grain, no lens softness).
- Shadows that do not match direction or softness.
- No contact: objects hover, no dust, no grass over feet.
- Edges with a halo or a dark line.
