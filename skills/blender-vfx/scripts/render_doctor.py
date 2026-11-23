"""Find what makes a Blender render slow, without changing anything.

Usage:
  blender -b file.blend -P render_doctor.py
  or exec inside an MCP code call.

Read-only. Prints one JSON line: the settings that matter for speed, and a
ranked list of findings, each with the fix and whether it risks quality.
Apply fixes only after the user approves them.
"""
import json

import bpy

HIGH, MED, LOW = 3, 2, 1


def main():
    s = bpy.context.scene
    r = s.render
    out = {"engine": r.engine, "res": [r.resolution_x, r.resolution_y, r.resolution_percentage],
           "frames": [s.frame_start, s.frame_end, s.frame_step],
           "fps": round(r.fps / r.fps_base, 3)}
    f = []

    def add(impact, issue, fix, quality_risk="none"):
        f.append({"impact": impact, "issue": issue, "fix": fix, "quality_risk": quality_risk})

    frames = max(1, (s.frame_end - s.frame_start) // max(1, s.frame_step) + 1)
    out["frame_count"] = frames

    if r.engine == "CYCLES":
        c = s.cycles
        prefs = None
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            backend = prefs.compute_device_type
            active = [d.name for d in prefs.devices if d.use and d.type != "CPU"]
        except Exception:
            backend, active = "unknown", []
        out["cycles"] = {"device": c.device, "backend": backend, "gpus": active[:3],
                         "samples": c.samples, "adaptive": c.use_adaptive_sampling,
                         "threshold": round(c.adaptive_threshold, 4), "denoise": c.use_denoising,
                         "bounces": [c.max_bounces, c.diffuse_bounces, c.glossy_bounces,
                                     c.transmission_bounces, c.volume_bounces, c.transparent_max_bounces],
                         "caustics": [c.caustics_reflective, c.caustics_refractive],
                         "clamp_indirect": c.sample_clamp_indirect}

        if c.device != "GPU" or backend in ("NONE", "unknown") or not active:
            add(HIGH, "Rendering on the CPU", "Preferences > System > Cycles Render Devices: pick METAL, OPTIX, CUDA, HIP or ONEAPI and tick the GPU; Render Properties > Device: GPU Compute")
        if not c.use_adaptive_sampling:
            add(HIGH, "Adaptive sampling off", "Turn on Noise Threshold (start 0.03; 0.05 for previews)")
        elif c.adaptive_threshold < 0.02:
            add(HIGH, f"Noise threshold very strict ({c.adaptive_threshold})", "Try 0.03 with denoising; compare a crop at 100 percent", "low")
        if c.samples > 1024:
            add(HIGH, f"Max samples {c.samples}", "Start at 512 with denoising; raise only where noise survives", "low")
        if not c.use_denoising:
            add(HIGH, "Denoising off", "Turn on OpenImageDenoise (GPU) with Albedo and Normal passes; Prefilter Accurate", "low")
        if c.max_bounces > 8:
            add(MED, f"Total bounces {c.max_bounces}", "Total 6, diffuse 3, glossy 3, volume 1; raise transmission only if glass or water goes black", "low")
        if c.transparent_max_bounces > 16:
            add(LOW, f"Transparent bounces {c.transparent_max_bounces}", "8 to 16 unless many layered alpha cards")
        if c.caustics_reflective or c.caustics_refractive:
            add(MED, "Caustics on", "Turn both off unless the shot shows caustics; fake them with a texture", "low")
        if c.sample_clamp_indirect == 0 or c.sample_clamp_indirect > 20:
            add(MED, "Indirect clamp off or high (fireflies force more samples)", "Clamp Indirect 10", "low")

    if not r.use_persistent_data:
        add(HIGH if frames > 1 else LOW, "Persistent Data off", "Render Properties > Performance > Final Render > Persistent Data (skips re-sync every frame)")
    if r.resolution_percentage > 100:
        add(HIGH, f"Resolution at {r.resolution_percentage} percent", "Render at delivery size (100 percent)")
    if r.use_motion_blur:
        add(LOW, "Motion blur on", "Keep for finals if it matches the plate; turn off for previews")
    if s.frame_step == 1 and frames > 48:
        add(LOW, "Every frame rendered", "Previews: frame step 2 or 3. Finals: all frames (frame interpolation causes artifacts in VFX)")

    # Geometry and modifiers
    sub_hi, disp_hi, polys, particles, hidden_render = [], 0, 0, 0, 0
    for o in s.objects:
        if o.hide_render:
            hidden_render += 1
            continue
        for m in o.modifiers:
            if m.type == "SUBSURF" and m.render_levels >= 3:
                sub_hi.append([o.name, m.render_levels])
            if m.type == "PARTICLE_SYSTEM":
                ps = m.particle_system.settings
                particles += ps.count * (ps.rendered_child_count if ps.child_type != "NONE" else 1)
        if o.type == "MESH" and o.data:
            polys += len(o.data.polygons)
        if getattr(o, "cycles", None) and getattr(o.cycles, "use_adaptive_subdivision", False):
            disp_hi += 1
    out["geometry"] = {"base_polys": polys, "particles": particles, "subsurf_render_3plus": sub_hi[:5],
                       "adaptive_subdiv_objects": disp_hi}
    if sub_hi:
        add(MED, f"{len(sub_hi)} objects with Subdivision render level 3+", "Level 1 to 2 for anything not in close up", "low")
    if particles > 2_000_000:
        add(MED, f"{particles:,} particles or hair strands", "Cut children for far objects; use instancing")

    # Volumes and lights
    vols = [o.name for o in s.objects if any(m.type == "FLUID" for m in o.modifiers) or o.type == "VOLUME"]
    if vols:
        step = getattr(s.cycles, "volume_step_rate", None) if r.engine == "CYCLES" else None
        add(MED, f"Volumes in scene ({len(vols)})", "Own View Layer; Volume Step Rate 2 to 4 in previews; check volume samples", "low")
        out["volumes"] = {"objects": vols[:5], "step_rate": step}
    lights = [o for o in s.objects if o.type == "LIGHT" and not o.hide_render]
    out["lights"] = len(lights)
    if len(lights) > 20 and r.engine == "CYCLES" and not s.cycles.use_light_tree:
        add(MED, f"{len(lights)} lights and Light Tree off", "Turn on Light Tree")

    # Textures
    big = [(i.name, i.size[0], i.size[1]) for i in bpy.data.images if i.size[0] * i.size[1] >= 4096 * 4096]
    mem_mb = sum(i.size[0] * i.size[1] * 4 for i in bpy.data.images if i.users) / 1e6
    out["textures"] = {"count": len(bpy.data.images), "4k_or_bigger": len(big), "approx_mb": round(mem_mb)}
    if big and not r.use_simplify:
        add(MED, f"{len(big)} textures 4K squared or larger", "Simplify > Texture Limit 2048 (1024 on 4 GB cards), or the 5.2+ texture cache", "low")

    # Output and compositing
    fmt = r.image_settings.file_format
    out["output"] = fmt
    if fmt in ("FFMPEG",) or getattr(r.image_settings, "media_type", "") == "VIDEO":
        add(MED, "Rendering straight to a video file", "Render an image sequence (EXR) and encode after; a crash then costs one frame")
    if fmt == "PNG" and r.image_settings.compression > 50:
        add(LOW, f"PNG compression {r.image_settings.compression}", "Use EXR half float with DWAA, or PNG compression 15")

    f.sort(key=lambda x: -x["impact"])
    for x in f:
        x["impact"] = {3: "high", 2: "medium", 1: "low"}[x["impact"]]
    out["findings"] = f
    return out


DOCTOR = json.dumps(main(), separators=(",", ":"))
print(DOCTOR)
