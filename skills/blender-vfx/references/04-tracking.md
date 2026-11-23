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
