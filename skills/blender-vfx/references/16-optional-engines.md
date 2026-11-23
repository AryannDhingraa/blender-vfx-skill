# Optional engines for hard footage

Blender's own tracker, compositor and Mantaflow cover most shots. Reach for these only when a shot needs them, and always ask before installing anything.

| Engine | Use it for | Notes |
| --- | --- | --- |
| COLMAP | Camera solves on long or messy shots, scanning a location, sparse point clouds to place the ground and walls | Free (BSD). Runs on CPU; GPU features need NVIDIA. Import cameras into Blender with a COLMAP importer add-on |
| OpenCV | Lens calibration from a checkerboard, forward-backward checks on tracks, frame analysis (blur, exposure, motion) | Free (Apache 2.0). Runs everywhere |
| CoTracker (Meta) | AI point tracking through occlusion and motion blur, to rescue tracks the normal tracker loses | Gives 2D tracks, not a camera solve. Check the licence before commercial use (non-commercial terms). Fast on NVIDIA; slow on CPU or Apple Silicon |
| SAM 2 (Meta) | AI masks that follow a person or object through the shot, for roto and holdouts | Check model licence. Edges on hair, smoke and motion blur still need refinement |
| Depth Anything V2 | Rough depth maps for fog, defocus or placing far objects | Gives relative depth, not real distances; scale it with a known measurement |
| Polychase (Blender extension) | Geometry tracking of objects and set pieces inside Blender | Optional; test on a copy |

## Rules

- One engine per job. Do not install several trackers at once; run the one the shot needs and compare its result with Blender's using `track_report.py` and a contact sheet.
- Check the user's hardware first (`11-hardware.md`). Many research models assume NVIDIA CUDA; installing on a Mac does not mean they run well.
- Keep a licence note for every engine and model in `asset-licenses.md`. Non-commercial tools cannot be used for paid or festival work that needs commercial rights.
- Process frames in batches on machines with 16 GB of memory or less.
