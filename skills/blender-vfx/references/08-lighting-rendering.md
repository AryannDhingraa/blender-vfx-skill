# Lighting and rendering

## Light to match the plate

- HDRI from a similar location (forest for forest), or one made from the grey and chrome ball reference. Rotate it until CG shadows point the same way as real shadows.
- A Sun lamp matched to the real sun's direction and softness (the real sun is about 0.5 degrees wide).
- Contrast sells scale. Flat light makes CG look fake; add a motivated back or rim light.
- Everything that glows or burns lights its surroundings, CG and plate.

## Integrate

- Shadow catcher: the rebuilt ground proxy, Object Properties, Visibility, Shadow Catcher, with Film set to Transparent.
- Holdout geometry for real foreground objects that pass in front of the CG.
- Scatter grass, debris, snow or dust around feet and contact points with Geometry Nodes, rendered as a matte to blend into the plate.
- Match the lens: undistort the plate if needed, render clean, redistort in compositing.
- Match motion blur (same shutter, Cycles shutter 0.5 for a 180 degree shutter) and depth of field (same focus distance and f-stop).
- Rolling shutter cameras: Cycles Motion Blur has a Rolling Shutter option to match skew.

## Passes and layers

- Separate View Layers: hero CG, FX (smoke, fire), shadows, atmosphere.
- Passes: Shadow Catcher, Emission, Volume, Mist, Z, Vector, Cryptomatte.
- Output multilayer OpenEXR, half float.

## Render settings (adjust with `11-hardware.md`)

- Cycles on the GPU. EEVEE for previz, far background elements and quick looks.
- Start: Noise Threshold 0.03, 512 max samples, OpenImageDenoise. Raise samples only where noise survives.
- Light Paths: total 6, diffuse 3, glossy 3, volume 1. Raise transmission and transparent only if glass or water renders black. Clamp Indirect around 10.
- Persistent Data on for animations.
- Render only the CG layers. Never re-render the plate.
- Static elements: render one frame and reuse it.
- Previews at 25 to 50 percent resolution. Full resolution, motion blur and high samples only for the approved final.

## Before every render

- State frame range, resolution, samples, estimated time, output path.
- Over the user's time limit: ask first.
- Render to `renders/shotID/v###/` so nothing gets overwritten.
- Long renders run headless on a saved copy: `blender -b shot_v003.blend -a`.
