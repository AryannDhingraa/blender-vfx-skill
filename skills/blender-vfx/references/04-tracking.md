# Camera tracking and set rebuild

Track every moving shot first, so CG sticks to the ground. All of this happens in Blender's Movie Clip Editor.

## Solve the camera

1. Load the plate (image sequence preferred). Build a proxy (50 percent) if playback is slow.
2. Set Sensor Width and Focal Length from the profile and shot notes. Wrong values give bent solves.
3. Place markers on high contrast, static points spread across the frame and the depth (near and far). Keep at least 8 visible on every frame. Never track moving people, water, reflections or leaves.
4. Track forwards and backwards. Delete short tracks that jump.
5. Solve Camera Motion. Target an average solve error under 0.3 px. Clean the worst markers and solve again. Refine focal length or distortion only if the error stays high.
6. Tripod pans have no parallax: use Tripod solving.
7. Setup Tracking Scene. Set the floor from 3 ground markers, the origin, and real scale from a measured distance.

Stop and ask the user after two failed solves. Options: retrack with different markers, 2D track instead, or reshoot.

## Classify the shot first

| Shot type | Solve |
| --- | --- |
| Locked off | No solve; 2D only |
| Pan or tilt on a tripod (no position change) | Tripod solve. Depth cannot be recovered from rotation alone |
| Handheld, walking, drone, vehicle (real parallax) | Full camera solve |
| Zoom during the shot | Avoid. If unavoidable, solve focal length per frame only after a clean fixed-lens attempt fails |
| Heavy rolling shutter or motion blur | Track the slower sections, add more markers, match rolling shutter in render |

Never stabilise the plate before tracking unless you keep the stabilisation transform and apply it back to the render.

## Check the solve, not just the number

Run `scripts/track_report.py` after every solve. It reports median and 95th percentile track error, tracks per frame, spread over a 3x3 image grid and track lifespans, with flags.

- A low average error alone does not prove a good solve. A solve can score well and still have the wrong depth or a bent floor.
- Holdout check: before solving, set aside 2 or 3 good tracks (mute them), solve, then unmute and check their error. High error on tracks the solver never saw means the camera is wrong.
- Forward-backward check: track a marker forwards, then backwards from its last frame. If the two paths disagree by more than about 1 px, delete it.
- 200 good, well spread markers beat 2000 weak ones. Replace lost markers as the camera moves.
- Visual check: put a few small cubes on the ground plane and a wall, render the contact sheet, and look for sliding.

## Lens calibration (optional, for zooms and wide lenses)

Film a printed checkerboard at the exact focal length, filling the frame at several angles. Calibrate with OpenCV (or Blender's distortion solve) and record the distortion values in `vfx-profile.md`. Reuse them for every shot at that focal length.

## Rebuild the set

- Model rough proxy geometry: ground, walls, rocks, trees. Use it for collisions, shadow catching and holdouts.
- When CG must change the real world (a split tree, a cracked wall), project the plate onto the proxy from the tracked camera (UV Project) and deform that.
- Real locations: scan with your own photos and photogrammetry (RealityScan, Meshroom). Do not extract 3D data from map services; their terms forbid it.

## Hard cases

- **Too shaky for 3D.** Render the CG from a static camera, 2D track the plate in the compositor, apply the track to the render, then add matching motion blur.
- **Moving props.** Object track, or match position and rotation by hand on key frames.
- **Fast action.** Shot in slow motion? Track at that speed, retime at the end.
- **Rolling shutter skew.** Track slower sections only, or use Cycles rolling shutter to match the CG.

## Record

Add the solve error, scale reference and any problem frames to `shot-log.md`.
