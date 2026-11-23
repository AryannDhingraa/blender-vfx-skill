# Review before showing anything

## How to review (cheap first)

1. Render 6 or more key frames at 50 percent: first, last, every contact moment, fastest motion, closest close up.
2. Put them on one contact sheet next to the plate and the reference. Look at the sheet, not single frames.
3. Check the brief's acceptance checks in `shot-log.md`.
4. Fix one thing, re-render only the affected frames, look again.
5. Watch at full speed and at delivery size (phone size for social).
6. Then ask for approval to run the final.

Open every render before describing it. Never report an image you have not looked at.

## Shot checklist

- [ ] Track holds on every frame, no sliding at contact points
- [ ] CG is the right size against people and objects in the plate
- [ ] Shadows match direction and softness of real shadows
- [ ] Contact blended: dust, grass, debris, sinking in, wet marks
- [ ] Real foreground sits in front of the CG where it should
- [ ] CG black level, white point and saturation match the plate
- [ ] No plastic surfaces; textures hold at the closest frame
- [ ] Glowing and burning things light their surroundings
- [ ] Defocus, motion blur, grain and lens distortion match the plate
- [ ] Camera shake and rolling shutter match
- [ ] Atmosphere in front of, around and behind the CG
- [ ] Strong light contrast on the hero
- [ ] Rigs, gear and stand-ins painted out
- [ ] Works in every delivery crop (16:9, 9:16)
- [ ] Nothing gives it away next to the reference
- [ ] Assets and sounds logged with licences

## Render file checks

- Frame count, resolution and frame range match the brief.
- No black, missing or duplicated frames.
- Neighbour-frame comparison for flicker spikes (`scripts/verify_output.py` reports frame stats; a sudden jump in average brightness on one frame is a dropped sample or a mixed-machine render).
