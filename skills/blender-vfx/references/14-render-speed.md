# Render speed

Goal: same image, less time. Run `scripts/render_doctor.py` first (read-only). It ranks what is slow in the scene and marks which fixes risk quality. Show the findings, get approval, then apply.

## Measure, change, compare

1. Pick one representative frame (the busiest one). Render it and write the time in `shot-log.md`.
2. Apply one group of fixes. Render the same frame.
3. Compare both at 100 percent zoom on a crop (shadows, glass, hair, edges). If it looks the same, keep the change.
4. Never change settings and start a long render without this test.

## 1. Don't render what you don't need (biggest wins, zero quality loss)

- Only the CG layers on a transparent film. Never re-render the plate.
- Locked-off shot with one moving part: render a still of the whole frame once, then only the moving region (Render Region) as an animation, and stack them.
- Static elements (background set, parked props): render one frame and reuse it.
- Hide collections that are off camera from render. Cull scattered objects outside the camera view.
- Previews at 25 to 50 percent resolution, frame step 2 or 3. Finals at delivery size, every frame.

## 2. Use the right hardware path (zero quality loss)

- GPU rendering: Metal (Apple), OptiX (NVIDIA RTX, also try on GTX), CUDA (older NVIDIA), HIP (AMD), oneAPI (Intel).
- Denoiser on the GPU (OpenImageDenoise, Use GPU ticked). On a CPU it can add seconds per frame.
- Compositor device: GPU.
- Persistent Data on for animations: Blender keeps meshes and textures between frames instead of rebuilding them.
- Render headless from a terminal (`blender -b file.blend -a`) so the interface uses no GPU memory.
- Keep the newest stable Blender; recent releases have made Cycles faster.

## 3. Sampling (no visible loss when tested)

- Adaptive sampling with Noise Threshold 0.03 for finals, 0.05 for previews. 0.01 is rarely needed under a denoiser.
- Max samples 128 to 512 with denoising. If noise remains, find its cause (caustics, fireflies, volumes) before adding samples.
- Denoise with Albedo and Normal passes, Prefilter Accurate.

## 4. Light paths (test on the busiest frame)

- Total 6 to 8, diffuse 3, glossy 3 to 4, volume 0 to 1, transparent 8 to 16.
- Transmission 8 only when glass or water is in shot; lower it otherwise.
- Caustics (reflective and refractive) off unless the shot shows them. Fake visible caustics with a texture.
- Filter Glossy 1.0. Clamp Indirect 10 (fireflies force extra samples).
- Many lights or emissive surfaces: Light Tree on.

## 5. Geometry and textures

- Instances (Alt+D) instead of copies. Decimate far objects. Subdivision render level 1 to 2 except close ups.
- Hair and curves: fewer children far away; linear curves render faster than smooth ones.
- Textures 1K to 2K away from camera. Simplify Texture Limit 2048 (1024 for 4 GB GPUs).
- Running out of memory makes renders crawl (system swap). Blender 5.2 and newer have a Cycles texture cache that cuts texture memory a lot for a small time cost; use it when memory is the limit.

## 6. Volumes and motion blur

- Volumes in their own View Layer. Raise Volume Step Rate (2 to 4) and check the look.
- Motion blur in Cycles costs time with deforming geometry. Keep it for finals when it must match the plate. Vector blur in the compositor is faster but fails on overlapping motion; test before using it on a VFX shot.

## 7. Output

- Render image sequences, never straight to video.
- Previews and beauty: EXR half float (DWAA compresses well). Data passes for compositing (Z, Vector, Cryptomatte): lossless EXR.
- PNG with high compression slows every frame write slightly.

## Tricks that cost quality (previews only, unless the user approves)

- Rendering every other frame and interpolating the rest: artifacts on edges, motion blur and anything fast. Not for VFX finals.
- Lower resolution then upscaling.
- Paid "auto optimiser" add-ons: test on a copy and compare frames.

## Optimise the computer (no quality loss)

### macOS

1. Plug in the charger. Battery settings: Low Power Mode off. If your Mac offers High Power mode, turn it on while rendering.
2. Keep it cool: hard surface or a stand, vents clear. Hot Macs slow down.
3. Quit memory-hungry apps (grading app, browser, chat apps). In Activity Monitor, Memory Pressure should stay green; yellow or red means swapping, which wrecks render speed.
4. Stop sleep during long renders: run `caffeinate -dimsu` in Terminal until the render ends.
5. Render headless from Terminal.
6. Keep projects and renders on the internal SSD or a fast external SSD, never in a cloud-synced folder while rendering.
7. Exclude render and cache folders from Spotlight (System Settings, Spotlight, Privacy).

### Windows with NVIDIA

1. Plug in. Power mode: Best performance.
2. Install the NVIDIA Studio driver.
3. NVIDIA Control Panel, Manage 3D settings, Program settings, blender.exe: High-performance NVIDIA processor; Power management mode: Prefer maximum performance.
4. Laptops: raise the back or use a cooling pad, clean vents. Watch GPU temperature; above about 85 C it throttles.
5. Close browsers, game launchers and overlays.
6. Render headless from Command Prompt.
7. Optional: exclude only the project's render and cache folders from antivirus real-time scanning. This trades a little security for write speed; never exclude whole drives.

### Linux

Proprietary NVIDIA driver, performance power profile, render headless, caches on a local SSD.

## Two machines

Use Flamenco (`11-hardware.md`). Split by shot or by layer, not by alternating frames between different GPU types.
