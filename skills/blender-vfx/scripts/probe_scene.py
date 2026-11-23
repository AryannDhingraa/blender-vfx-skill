"""Compact scene summary for agents. Run inside Blender.

Usage:
  blender -b file.blend -P probe_scene.py
  or paste into an MCP "execute Blender code" call.

Prints one JSON line (and returns it as `PROBE` when executed via exec).
Output is bounded: counts plus the top few heavy items, never full lists.
"""
import json
import bpy

TOP_N = 5


def _evaluated_polys(obj, depsgraph):
    try:
        ev = obj.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        n = len(mesh.polygons)
        ev.to_mesh_clear()
        return n
    except Exception:
        return 0


def probe():
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    render = scene.render
    out = {
        "blender": bpy.app.version_string,
        "file": bpy.data.filepath or "(unsaved)",
        "scene": scene.name,
        "engine": render.engine,
        "resolution": [render.resolution_x, render.resolution_y, render.resolution_percentage],
        "fps": round(render.fps / render.fps_base, 3),
        "frames": [scene.frame_start, scene.frame_end, scene.frame_current],
        "units": [scene.unit_settings.system, scene.unit_settings.scale_length],
        "view_transform": scene.view_settings.view_transform,
        "film_transparent": render.film_transparent,
        "motion_blur": render.use_motion_blur,
    }

    if render.engine == "CYCLES":
        c = scene.cycles
        out["cycles"] = {
            "device": getattr(c, "device", None),
            "samples": c.samples,
            "adaptive_threshold": round(c.adaptive_threshold, 4) if c.use_adaptive_sampling else None,
            "denoise": c.use_denoising,
            "max_bounces": c.max_bounces,
            "texture_limit": c.texture_limit_render if render.use_simplify else None,
        }

    cam = scene.camera
    if cam and cam.type == "CAMERA":
        d = cam.data
        out["camera"] = {
            "name": cam.name,
            "focal_mm": round(d.lens, 2),
            "sensor_mm": round(d.sensor_width, 2),
            "dof": d.dof.use_dof,
            "f_stop": round(d.dof.aperture_fstop, 2) if d.dof.use_dof else None,
        }

    counts = {}
    heavy = []
    no_mat = 0
    unapplied_scale = 0
    for obj in scene.objects:
        counts[obj.type] = counts.get(obj.type, 0) + 1
        if obj.type == "MESH":
            heavy.append((_evaluated_polys(obj, depsgraph), obj.name))
            if not obj.material_slots or not any(s.material for s in obj.material_slots):
                no_mat += 1
            if any(abs(s - 1.0) > 1e-4 for s in obj.scale):
                unapplied_scale += 1
    heavy.sort(reverse=True)
    out["objects"] = counts
    out["polys_total"] = sum(p for p, _ in heavy)
    out["heaviest"] = [[n, p] for p, n in heavy[:TOP_N]]
    out["meshes_without_material"] = no_mat
    out["meshes_unapplied_scale"] = unapplied_scale

    imgs = [(i.size[0] * i.size[1], i.name, list(i.size)) for i in bpy.data.images if i.size[0]]
    imgs.sort(reverse=True)
    out["images"] = {"count": len(imgs), "largest": [[n, s] for _, n, s in imgs[:TOP_N]]}

    sims = []
    for obj in scene.objects:
        for m in obj.modifiers:
            if m.type in {"FLUID", "CLOTH", "SOFT_BODY", "DYNAMIC_PAINT", "OCEAN"}:
                baked = None
                pc = getattr(m, "point_cache", None)
                if pc is not None:
                    baked = pc.is_baked
                sims.append([obj.name, m.type, baked])
    if scene.rigidbody_world:
        sims.append(["RigidBodyWorld", "RIGID_BODY", scene.rigidbody_world.point_cache.is_baked])
    out["simulations"] = sims[:10]

    layers = []
    for vl in scene.view_layers:
        passes = [p for p in ("use_pass_z", "use_pass_mist", "use_pass_vector", "use_pass_emit",
                              "use_pass_shadow_catcher", "use_pass_cryptomatte_object")
                  if getattr(vl, p, False)]
        layers.append([vl.name, vl.use, [p.replace("use_pass_", "") for p in passes]])
    out["view_layers"] = layers

    clips = []
    for clip in bpy.data.movieclips:
        rec = clip.tracking.reconstruction
        clips.append([clip.name, len(clip.tracking.tracks), rec.is_valid,
                      round(rec.average_error, 3) if rec.is_valid else None])
    out["clips"] = clips[:5]
    return out


PROBE = json.dumps(probe(), separators=(",", ":"))
print(PROBE)
