"""Build an asset from scratch when no free download fits: real scale,
procedural materials, low polycount. Fallback for the asset search.

  blender -b shot.blend -P procedural_asset.py -- --kind rock --size 0.4 --seed 3 \
      [--location 0,2,0] [--count 12] [--preview _review/asset.png]

Kinds: rock, debris (a scatter of small rocks), crate, brick_wall, plank.
--preview renders a small Cycles still of just the new objects for approval
and restores every render setting afterwards. Prints one JSON line.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"kind": "rock", "size": 0.4, "seed": 1, "location": "0,0,0", "count": 10, "preview": None, "name": None}
    for i in range(0, len(argv) - 1):
        k = argv[i].lstrip("-")
        if argv[i].startswith("--") and k in a:
            a[k] = argv[i + 1]
    a["size"], a["seed"], a["count"] = float(a["size"]), int(a["seed"]), int(a["count"])
    a["location"] = Vector([float(x) for x in a["location"].split(",")])
    return a


def _mat(name, kind):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    if kind == "brick":
        tex = nt.nodes.new("ShaderNodeTexBrick")
        tex.inputs["Color1"].default_value = (0.34, 0.12, 0.07, 1)
        tex.inputs["Color2"].default_value = (0.25, 0.09, 0.05, 1)
        tex.inputs["Mortar"].default_value = (0.55, 0.53, 0.5, 1)
        tex.inputs["Scale"].default_value = 4.0
        nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        b.inputs["Roughness"].default_value = 0.9
        return mat
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = {"rock": 6.0, "wood": 2.0}.get(kind, 6.0)
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    lo, hi = {"rock": ((0.12, 0.115, 0.11, 1), (0.38, 0.36, 0.33, 1)),
              "wood": ((0.20, 0.11, 0.05, 1), (0.45, 0.28, 0.14, 1))}[kind]
    ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = lo, hi
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.38, 0.62
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = 0.6, 0.95
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], b.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return mat


def _link(name, bm, mat, loc):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    if hasattr(me, "set_sharp_from_angle"):  # Blender 4.1+: keep facets crisp
        me.set_sharp_from_angle(angle=math.radians(35))
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _uv_bm():
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    return bm


def rock(name, size, rng, loc):
    bm = _uv_bm()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=size / 2, calc_uvs=True)
    axis = rng.uniform(0.65, 1.25, 3)
    dirs = rng.normal(size=(9, 3))
    dirs /= np.linalg.norm(dirs, axis=1)[:, None]
    cuts = rng.uniform(0.22, 0.34, len(dirs)) * size
    for v in bm.verts:
        p = np.array(v.co) * axis
        for d, c in zip(dirs, cuts):  # flat facets like a broken stone
            depth = (p @ d) - c
            if depth > 0:
                p -= d * depth
        p *= 1 + rng.normal(0, 0.012)
        v.co = Vector(p)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, 0, -min(v.co.z for v in bm.verts))))
    return _link(name, bm, _mat("vfx_rock", "rock"), loc)


def crate(name, size, rng, loc):
    bm = _uv_bm()
    bmesh.ops.create_cube(bm, size=size, calc_uvs=True)
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=size * 0.02, segments=2, affect="EDGES")
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, 0, size / 2)))
    return _link(name, bm, _mat("vfx_wood", "wood"), loc)


def plank(name, size, rng, loc):
    bm = _uv_bm()
    bmesh.ops.create_cube(bm, size=1, calc_uvs=True)
    bmesh.ops.scale(bm, verts=bm.verts, vec=Vector((size, size * 0.12, size * 0.025)))
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=size * 0.004, segments=1, affect="EDGES")
    return _link(name, bm, _mat("vfx_wood", "wood"), loc)


def brick_wall(name, size, rng, loc):
    bm = _uv_bm()
    bmesh.ops.create_cube(bm, size=1, calc_uvs=True)
    bmesh.ops.scale(bm, verts=bm.verts, vec=Vector((size, 0.23, size * 0.6)))
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, 0, size * 0.3)))
    return _link(name, bm, _mat("vfx_brick", "brick"), loc)


def preview(objs, path):
    scene = bpy.context.scene
    r = scene.render
    saved = (scene.camera, r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath,
             r.image_settings.file_format, scene.cycles.samples if hasattr(scene, "cycles") else None, scene.world)
    hidden = [o for o in scene.objects if o not in objs and o.type in {"MESH", "CURVE"} and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    lo = Vector([min((o.matrix_world @ Vector(c))[i] for o in objs for c in o.bound_box) for i in range(3)])
    hi = Vector([max((o.matrix_world @ Vector(c))[i] for o in objs for c in o.bound_box) for i in range(3)])
    centre, rad = (lo + hi) / 2, max((hi - lo).length / 2, 0.05)
    cam = bpy.data.objects.new("vfx_preview_cam", bpy.data.cameras.new("vfx_preview_cam"))
    scene.collection.objects.link(cam)
    cam.location = centre + Vector((rad * 2.2, -rad * 2.6, rad * 1.6))
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    sun = bpy.data.objects.new("vfx_preview_sun", bpy.data.lights.new("vfx_preview_sun", "SUN"))
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    sun.data.energy = 3.0
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("vfx_preview_world")
    world.color = (0.08, 0.08, 0.09)
    scene.world, scene.camera = world, cam
    r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage = "CYCLES", 320, 320, 100
    scene.cycles.samples, scene.cycles.device = 32, "CPU"
    r.image_settings.file_format, r.filepath = "PNG", os.path.abspath(path)
    try:
        bpy.ops.render.render(write_still=True)
    finally:
        (scene.camera, r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath,
         r.image_settings.file_format, samples, scene.world) = saved
        if samples is not None:
            scene.cycles.samples = samples
        for o in hidden:
            o.hide_render = False
        for ob in (cam, sun):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.worlds.remove(world)
    return os.path.abspath(path)


def main():
    a = args()
    rng = np.random.default_rng(a["seed"])
    make = {"rock": rock, "crate": crate, "plank": plank, "brick_wall": brick_wall}
    objs = []
    if a["kind"] == "debris":
        for i in range(a["count"]):
            s = a["size"] * rng.uniform(0.2, 1.0)
            off = Vector((rng.normal(0, a["size"] * 2), rng.normal(0, a["size"] * 2), 0))
            objs.append(rock(f"{a['name'] or 'debris'}_{i:02d}", s, rng, a["location"] + off))
    elif a["kind"] in make:
        objs.append(make[a["kind"]](a["name"] or f"vfx_{a['kind']}", a["size"], rng, a["location"]))
    else:
        raise SystemExit(json.dumps({"error": f"unknown kind {a['kind']}"}))
    polys = sum(len(o.data.polygons) for o in objs)
    dims = [round(x, 3) for x in objs[0].dimensions]
    res = {"kind": a["kind"], "objects": [o.name for o in objs], "polygons": polys, "size_m": dims,
           "materials": sorted({m.name for o in objs for m in o.data.materials})}
    if a["preview"]:
        res["preview"] = preview(objs, a["preview"])
    print(json.dumps(res, separators=(",", ":")))
    return res


RESULT = main()
