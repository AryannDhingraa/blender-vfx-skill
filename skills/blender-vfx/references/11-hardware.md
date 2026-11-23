# Hardware: make it fit the user's machines

Read the profile, pick the tier, apply its settings. Run the free Blender Benchmark on each machine once to see real speeds before splitting work.

## Tiers

| Tier | Example | Use it for | Key settings |
| --- | --- | --- | --- |
| Apple Silicon | M1 to M4 chips, 16 to 36 GB unified memory | Everything except huge sims | Cycles on Metal GPU. Memory is shared by CPU and GPU: quit other apps while rendering |
| NVIDIA RTX, 8 GB VRAM or more | RTX 3060 and up | Final renders, fast previews | OptiX, OptiX denoiser |
| NVIDIA low VRAM | GTX 16 series, 4 GB | Light layers, tests, overnight CPU bakes | CUDA first, then try OptiX. Simplify Texture Limit 1024 |
| CPU only | No usable GPU | Simulation bakes, small renders | Lower samples, rely on the denoiser, render overnight |

## Universal speedups (biggest first)

1. Stock elements instead of huge simulations.
2. Render only the CG layers on a transparent film. Never re-render the plate.
3. Render static elements once as a still.
4. Previews at 25 to 50 percent resolution. Finals at the delivery resolution, not higher.
5. Noise Threshold 0.03 plus OpenImageDenoise before adding samples.
6. Light Paths: total 6, diffuse 3, glossy 3, volume 1.
7. Simplify Texture Limit: 2048 for 8 GB or more, 1024 for 4 GB.
8. Persistent Data on. Instance repeated objects. Decimate far models. 1K to 2K textures away from camera.
9. Volumes in their own View Layer with a higher Volume Step Rate.
10. Motion blur and full samples only on the approved final.

## Memory

- Unified memory machines: close the grading app and browsers during renders.
- Out of memory: lower texture limit, split View Layers, render in tiles or halves, move volumes to a separate pass.
- Caches and renders on a fast external SSD with lots of space.

## Two or more machines (Flamenco)

Flamenco is Blender's free render farm manager.

1. Same Blender version on every machine. Latest GPU drivers on Windows.
2. A shared folder over the network (SMB) that every machine can read and write.
3. Run the Flamenco Manager on one machine and a Worker on each.
4. Set two-way variables so each OS maps the shared folder path correctly.
5. Submit from the Flamenco panel in Output Properties.
6. Render a whole shot or a whole layer on one machine type where possible. Different GPU backends can produce slightly different noise, which flickers when frames are mixed. Check with the neighbour-frame comparison in `12-review-checklist.md`.

## Simulation

Mantaflow runs on the CPU. Iterate small on the main machine, bake the final overnight on whichever machine is free.
