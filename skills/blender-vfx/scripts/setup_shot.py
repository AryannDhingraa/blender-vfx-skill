"""Set up a Blender scene and folders for a VFX shot in one call.

Usage (headless):
  blender -b -P setup_shot.py -- --root ~/vfx/myfilm --shot SHOT010 \
      --fps 24 --res 3840x2160 --sensor 23.5 --focal 16 --tier apple
Or exec inside an MCP code call after setting sys.argv.

Creates the standard project layout (references/15-project-structure.md) with
<shot> subfolders and a README.md if missing, sets metric
units, frame rate, resolution, camera sensor and focal length, Standard view
transform for plate work, Cycles defaults for the hardware tier, multilayer
EXR output and the integration passes, then saves <shot>_v001.blend.
Never overwrites an existing .blend: it picks the next free version.
Prints one JSON line with what it did.
"""
import argparse
import json
import os
import sys

import bpy

TIERS = {
    # device, texture limit (0 = off)
    "apple": ("METAL", "2048"),
    "rtx": ("OPTIX", "0"),
    "lowvram": ("CUDA", "1024"),
    "cpu": ("NONE", "2048"),
}


def parse(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--shot", required=True)
    p.add_argument("--fps", type=float, default=24)
    p.add_argument("--res", default="1920x1080")
    p.add_argument("--sensor", type=float, default=36.0)
    p.add_argument("--focal", type=float, default=35.0)
    p.add_argument("--tier", choices=sorted(TIERS), default="cpu")
    p.add_argument("--frames", default="1-120")
    p.add_argument("--full-cg", action="store_true", help="use AgX instead of Standard")
    return p.parse_args(argv)


def set_gpu(device_type):
    if device_type == "NONE":
        return "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = device_type
        prefs.get_devices()
        found = False
        for d in prefs.devices:
            d.use = d.type == device_type
            found = found or d.use
        return "GPU" if found else "CPU"
    except Exception:
        return "CPU"


def next_version(folder, shot):
    v = 1
    while os.path.exists(os.path.join(folder, f"{shot}_v{v:03d}.blend")):
        v += 1
    return v


def main(a):
    root = os.path.expanduser(a.root)
    for sub in ("00_brief", "01_source", "04_assets", "09_deliver", "scripts", "logs",
                "_review", "_tmp", "_archive"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    for sub in ("02_plates", "03_track", "05_blend", "06_cache", "07_renders", "08_comp"):
        os.makedirs(os.path.join(root, sub, a.shot), exist_ok=True)
    readme = os.path.join(root, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w") as fh:
            fh.write(f"# {os.path.basename(root.rstrip('/'))}\n\nStatus: set up {a.shot}.\nLatest output: none yet.\n"
                     "Layout: see the blender-vfx skill, references/15-project-structure.md.\n")

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    w, h = (int(x) for x in a.res.lower().split("x"))
    r = scene.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
    fps = a.fps
    r.fps, r.fps_base = (round(fps), 1.0) if float(fps).is_integer() else (round(fps), round(fps) / fps)
    start, end = (int(x) for x in a.frames.split("-"))
    scene.frame_start, scene.frame_end = start, end

    cam = scene.camera
    if cam is None:
        cam_data = bpy.data.cameras.new("ShotCam")
        cam = bpy.data.objects.new("ShotCam", cam_data)
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = a.sensor
    cam.data.lens = a.focal

    scene.view_settings.view_transform = "AgX" if a.full_cg else "Standard"
    r.film_transparent = not a.full_cg

    r.engine = "CYCLES"
    c = scene.cycles
    device_type, tex_limit = TIERS[a.tier]
    c.device = set_gpu(device_type)
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.03
    c.samples = 512
    c.use_denoising = True
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces, c.volume_bounces = 6, 3, 3, 1
    c.sample_clamp_indirect = 10.0
    r.use_persistent_data = True
    if tex_limit != "0":
        r.use_simplify = True
        c.texture_limit_render = tex_limit
        c.texture_limit = tex_limit

    vl = scene.view_layers[0]
    for attr in ("use_pass_z", "use_pass_mist", "use_pass_vector", "use_pass_emit",
                 "use_pass_shadow_catcher", "use_pass_cryptomatte_object"):
        if hasattr(vl, attr):
            setattr(vl, attr, True)

    ims = r.image_settings
    if hasattr(ims, "media_type"):  # Blender 5.x
        ims.media_type = "MULTI_LAYER_IMAGE"
    else:  # Blender 4.x
        ims.file_format = "OPEN_EXR_MULTILAYER"
    ims.color_depth = "16"
    blend_dir = os.path.join(root, "05_blend", a.shot)
    v = next_version(blend_dir, a.shot)
    render_dir = os.path.join(root, "07_renders", a.shot, f"v{v:03d}")
    os.makedirs(render_dir, exist_ok=True)
    r.filepath = os.path.join(render_dir, f"{a.shot.lower()}_")

    path = os.path.join(blend_dir, f"{a.shot}_v{v:03d}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)

    print(json.dumps({"saved": path, "fps": fps, "res": [w, h], "sensor": a.sensor,
                      "focal": a.focal, "device": c.device, "tier": a.tier,
                      "view": scene.view_settings.view_transform}, separators=(",", ":")))


if __name__ == "__main__":
    main(parse(sys.argv))
