"""Break part of a wall or object, only where the impact is.

  blender -b shot.blend -P destruction.py -- --object proxy_1 --impact 0,0,1.2 \
      --radius 0.6 --pieces 24 --frame 20 --end 80 [--direction 0,1,0] [--speed 12] [--bake]

Only a rough sphere around the impact is cut out and fractured, so the rest
of the wall stays one static object: fewer pieces, faster sims, smaller
caches. Steps: noisy cutter, boolean hole in the wall, the removed chunk
split into --pieces by random cuts weighted towards the impact, inner faces
given a concrete material, rigid bodies with convex hulls that wake at
--frame, and a hidden impactor that flies through along --direction.
Baking is only done with --bake (ask first when it will take long).
Prints one JSON line.
"""
import json
import math
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"object": None, "impact": None, "impact_object": None, "radius": 0.6, "pieces": 20, "seed": 1,
         "frame": 1, "end": 60, "direction": None, "speed": 10.0, "density": 2400.0, "ground": None,
         "bake": False, "noise": 0.25}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-").replace("-", "_")
        if k == "bake":
            a["bake"] = True
            i += 1
            continue
        if k in a:
            a[k] = argv[i + 1]
            i += 2
        else:
            i += 1
    for k in ("radius", "speed", "density", "noise"):
        a[k] = float(a[k])
    for k in ("pieces", "seed", "frame", "end"):
        a[k] = int(a[k])
    for k in ("impact", "direction"):
        if a[k]:
            a[k] = Vector([float(x) for x in a[k].split(",")])
    return a


def inner_material():
    mat = bpy.data.materials.get("vfx_inner_concrete")
    if mat:
        return mat
    mat = bpy.data.materials.new("vfx_inner_concrete")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.18, 0.17, 0.16, 1)
    ramp.color_ramp.elements[1].color = (0.42, 0.40, 0.37, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.95
    return mat


def cutter(center, radius, noise, rng, mat):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=radius)
    for v in bm.verts:
        v.co *= 1.0 + noise * (rng.random() - 0.5)
        v.co += center
    me = bpy.data.meshes.new("vfx_cutter")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new("vfx_cutter", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def boolean(target, other, op):
    mod = target.modifiers.new("vfx_bool", "BOOLEAN")
    mod.operation, mod.object, mod.solver = op, other, "EXACT"
    with bpy.context.temp_override(object=target, active_object=target, selected_objects=[target]):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def volume(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    v = abs(bm.calc_volume(signed=True))
    bm.free()
    return v


def split(bm, co, no, inner_idx):
    halves = []
    for keep in ("outer", "inner"):
        b = bm.copy()
        geom = b.verts[:] + b.edges[:] + b.faces[:]
        r = bmesh.ops.bisect_plane(b, geom=geom, plane_co=co, plane_no=no, dist=1e-6,
                                   clear_inner=keep == "outer", clear_outer=keep == "inner")
        cut = [e for e in r["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if cut:
            new = bmesh.ops.edgeloop_fill(b, edges=cut)["faces"] or bmesh.ops.holes_fill(b, edges=cut)["faces"]
            for f in new:
                f.material_index = inner_idx
        bmesh.ops.recalc_face_normals(b, faces=b.faces[:])
        halves.append(b)
    return halves


def fracture(chunk_me, n, impact, radius, rng, inner_idx):
    bm = bmesh.new()
    bm.from_mesh(chunk_me)
    pieces = [bm]
    tries = 0
    while len(pieces) < n and tries < n * 8:
        tries += 1
        vols = [abs(p.calc_volume(signed=True)) for p in pieces]
        i = int(np.argmax(vols))
        p = pieces[i]
        pts = np.array([v.co[:] for v in p.verts])
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        co = np.clip(np.array(impact) + rng.normal(0, radius * 0.35, 3), lo, hi)
        no = rng.normal(size=3)
        no /= np.linalg.norm(no)
        a, b = split(p, Vector(co), Vector(no), inner_idx)
        va, vb = abs(a.calc_volume(signed=True)), abs(b.calc_volume(signed=True))
        if min(va, vb) < vols[i] * 0.03 or abs(va + vb - vols[i]) > vols[i] * 0.02:
            a.free()
            b.free()
            continue
        p.free()
        pieces[i:i + 1] = [a, b]
    return pieces


def add_rigid(ob, kind, shape, mass=None):
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.rigidbody.object_add(type=kind)
    rb = ob.rigid_body
    rb.collision_shape = shape
    rb.friction, rb.restitution = 0.6, 0.1
    rb.use_margin, rb.collision_margin = True, 0.004
    if mass is not None:
        rb.mass = mass
    return rb


def main():
    a = args()
    scene = bpy.context.scene
    rng = np.random.default_rng(a["seed"])
    wall = bpy.data.objects[a["object"]]
    impact = a["impact"] or bpy.data.objects[a["impact_object"]].matrix_world.translation.copy()
    if wall.type != "MESH":
        raise SystemExit("object must be a mesh")
    vol0 = volume(wall.data)
    if vol0 <= 1e-9:
        raise SystemExit(json.dumps({"error": "object has no volume; give the proxy some thickness"}))
    mat = inner_material()
    if mat.name not in wall.data.materials:
        wall.data.materials.append(mat)
    inner_idx = list(wall.data.materials).index(mat)

    cut = cutter(impact, a["radius"], a["noise"], rng, mat)
    chunk = wall.copy()
    chunk.data = wall.data.copy()
    chunk.name = f"{wall.name}_chunk"
    scene.collection.objects.link(chunk)
    boolean(wall, cut, "DIFFERENCE")
    boolean(chunk, cut, "INTERSECT")
    bpy.data.objects.remove(cut, do_unlink=True)
    v_wall, v_chunk = volume(wall.data), volume(chunk.data)
    if v_chunk < 1e-9:
        raise SystemExit(json.dumps({"error": "impact sphere does not touch the object"}))

    mw = chunk.matrix_world.copy()
    chunk.data.transform(mw)
    pieces = fracture(chunk.data, a["pieces"], impact, a["radius"], rng, inner_idx)
    mats = list(chunk.data.materials)
    bpy.data.objects.remove(chunk, do_unlink=True)

    if scene.rigidbody_world is None:
        with bpy.context.temp_override(scene=scene):
            bpy.ops.rigidbody.world_add()
    rbw = scene.rigidbody_world
    rbw.point_cache.frame_start = max(scene.frame_start, a["frame"] - 1)
    rbw.point_cache.frame_end = a["end"]
    rbw.substeps_per_frame = 10
    rbw.solver_iterations = 20

    objs, v_sum = [], 0.0
    for k, b in enumerate(pieces):
        me = bpy.data.meshes.new(f"{wall.name}_piece_{k:03d}")
        b.to_mesh(me)
        b.free()
        for m in mats:
            me.materials.append(m)
        c = sum((v.co for v in me.vertices), Vector()) / len(me.vertices)
        me.transform(Matrix.Translation(-c))
        ob = bpy.data.objects.new(me.name, me)
        ob.location = c
        scene.collection.objects.link(ob)
        v = volume(me)
        v_sum += v
        add_rigid(ob, "ACTIVE", "CONVEX_HULL", mass=max(0.05, v * a["density"]))
        ob.rigid_body.kinematic = True
        ob.keyframe_insert('rigid_body.kinematic', frame=a["frame"] - 1)
        ob.rigid_body.kinematic = False
        ob.keyframe_insert('rigid_body.kinematic', frame=a["frame"])
        objs.append(ob)

    add_rigid(wall, "PASSIVE", "MESH")
    lo_z = min((wall.matrix_world @ Vector(c)).z for c in wall.bound_box)
    ground = bpy.data.objects.get(a["ground"]) if a["ground"] else None
    if ground is None:
        bpy.ops.mesh.primitive_plane_add(size=50, location=(impact.x, impact.y, lo_z))
        ground = bpy.context.active_object
        ground.name = "vfx_ground_collider"
        ground.hide_render = True
    add_rigid(ground, "PASSIVE", "BOX")

    d = a["direction"]
    if d is None:
        cam = scene.camera
        d = (impact - cam.matrix_world.translation) if cam else Vector((0, 1, 0))
    d = d.normalized()
    bpy.ops.mesh.primitive_uv_sphere_add(radius=a["radius"] * 0.35, location=impact - d * a["radius"] * 2)
    imp = bpy.context.active_object
    imp.name = "vfx_impactor"
    imp.hide_render = True
    fps = scene.render.fps / scene.render.fps_base
    travel = a["speed"] / fps
    imp.keyframe_insert("location", frame=a["frame"] - 2)
    imp.location = impact - d * a["radius"] * 2 + d * travel * 8
    imp.keyframe_insert("location", frame=a["frame"] + 6)
    add_rigid(imp, "PASSIVE", "SPHERE")
    imp.rigid_body.kinematic = True

    res = {"pieces": len(objs), "requested": a["pieces"], "volume_m3": {"original": round(vol0, 4),
           "wall_after": round(v_wall, 4), "chunk": round(v_chunk, 4), "pieces_sum": round(v_sum, 4)},
           "volume_ok": abs(v_sum - v_chunk) <= 0.02 * v_chunk and abs(v_wall + v_chunk - vol0) <= 0.03 * vol0,
           "frames": [a["frame"], a["end"]], "baked": False, "objects_prefix": f"{wall.name}_piece_"}
    if a["bake"]:
        with bpy.context.temp_override(scene=scene, point_cache=rbw.point_cache):
            bpy.ops.ptcache.bake(bake=True)
        res["baked"] = rbw.point_cache.is_baked
    print(json.dumps(res, separators=(",", ":")))
    return res


RESULT = main()
