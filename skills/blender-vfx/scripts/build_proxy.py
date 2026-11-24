"""Rebuild just enough of a real place to interact with: proxy walls and
floors fitted to tracked 3D points, with the plate projected onto them so a
wall can crack, break or catch shadows and still look like the footage.

  blender -b shot.blend -P build_proxy.py -- --object TrackedPoints --planes 2 \
      --thickness 0.25 --plate 02_plates/sh010/plate_0050.png --frame 50

Points come from (pick one):
  --object NAME    a mesh whose vertices are the 3D points (Clip editor:
                   Reconstruction > 3D Markers to Mesh makes one)
  --empties PREFIX empties named PREFIX* (Link Empty to Track)
  --points FILE    JSON list of [x, y, z] (for COLMAP or other solvers)
Fits up to --planes planes with RANSAC, sized to their points plus --margin,
thickened by --thickness, facing the camera. With --plate and --frame the
plate is projected from the camera at that frame and baked into UVs, so the
texture sticks to the geometry when it moves. Prints one JSON line.
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
    a = {"object": None, "empties": None, "points": None, "planes": 1, "thickness": 0.2, "margin": 0.1,
         "tol": None, "name": "proxy", "plate": None, "frame": None, "seed": 1}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if k in a:
            v = argv[i + 1]
            a[k] = type(a[k])(v) if isinstance(a[k], (int, float)) and a[k] is not None else v
            i += 2
        else:
            i += 1
    for k in ("planes", "frame", "seed"):
        if a[k] is not None:
            a[k] = int(a[k])
    for k in ("thickness", "margin", "tol"):
        if a[k] is not None:
            a[k] = float(a[k])
    return a


def gather(a):
    if a["points"]:
        with open(a["points"]) as f:
            return np.array(json.load(f), dtype=float)
    if a["object"]:
        ob = bpy.data.objects[a["object"]]
        mw = ob.matrix_world
        return np.array([list(mw @ v.co) for v in ob.data.vertices])
    if a["empties"]:
        return np.array([list(o.matrix_world.translation) for o in bpy.data.objects
                         if o.type == "EMPTY" and o.name.startswith(a["empties"])])
    raise SystemExit("give --object, --empties or --points")


def fit_plane(P):
    c = P.mean(axis=0)
    _, s, vt = np.linalg.svd(P - c)
    return c, vt[2], s


def ransac_planes(P, n_planes, tol, rng, min_pts=6):
    left, planes = np.arange(len(P)), []
    for _ in range(n_planes):
        if len(left) < min_pts:
            break
        best = None
        for _ in range(400):
            idx = rng.choice(left, 3, replace=False)
            a, b, c = P[idx]
            nrm = np.cross(b - a, c - a)
            if np.linalg.norm(nrm) < 1e-9:
                continue
            nrm /= np.linalg.norm(nrm)
            d = np.abs((P[left] - a) @ nrm)
            inl = left[d < tol]
            if best is None or len(inl) > len(best):
                best = inl
        if best is None or len(best) < min_pts:
            break
        for _ in range(3):  # refine: fit, measure the real noise, tighten the band
            c, nrm, _ = fit_plane(P[best])
            r = np.abs((P[best] - c) @ nrm)
            band = min(tol, max(0.003, 3 * 1.4826 * float(np.median(r))))
            d = np.abs((P[left] - c) @ nrm)
            new = left[d < band]
            if len(new) < min_pts:
                break
            best = new
        c, nrm, _ = fit_plane(P[best])
        rms = float(np.sqrt(np.mean(((P[best] - c) @ nrm) ** 2)))
        planes.append((c, nrm, best, rms))
        left = np.setdiff1d(left, best)
    return planes, left


def make_wall(name, c, nrm, pts, margin, thick, cam_pos):
    nrm = Vector(nrm)
    if cam_pos is not None and nrm.dot(Vector(cam_pos) - Vector(c)) < 0:
        nrm = -nrm
    up = Vector((0, 0, 1)) if abs(nrm.z) < 0.9 else Vector((0, 1, 0))
    u = up.cross(nrm).normalized()
    v = nrm.cross(u).normalized()
    rel = pts - c
    pu, pv = rel @ np.array(u), rel @ np.array(v)
    u0, u1 = pu.min() - margin, pu.max() + margin
    v0, v1 = pv.min() - margin, pv.max() + margin
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    corners = [Vector(c) + u * a + v * b for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
    verts = [bm.verts.new(p) for p in corners]
    face = bm.faces.new(verts)
    face.normal_update()
    if face.normal.dot(nrm) < 0:
        face.normal_flip()
    if thick > 0:  # thickness goes away from the camera, so the front face stays on the points
        r = bmesh.ops.extrude_face_region(bm, geom=[face])
        moved = [e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=moved, vec=-nrm * thick)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob, (u1 - u0, v1 - v0), list(nrm)


def project_plate(ob, plate, frame):
    scene = bpy.context.scene
    cam = scene.camera
    if cam is None:
        return "no scene camera; projection skipped"
    scene.frame_set(frame)
    proj = cam.copy()
    proj.data = cam.data.copy()
    proj.animation_data_clear()
    proj.constraints.clear()
    proj.matrix_world = cam.matrix_world.copy()
    proj.name = f"{ob.name}_projector_f{frame}"
    scene.collection.objects.link(proj)
    if not ob.data.uv_layers:
        ob.data.uv_layers.new(name="projection")
    mod = ob.modifiers.new("project", "UV_PROJECT")
    mod.projectors[0].object = proj
    r = scene.render
    mod.aspect_x, mod.aspect_y = r.resolution_x * r.pixel_aspect_x, r.resolution_y * r.pixel_aspect_y
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    mat = bpy.data.materials.new(f"{ob.name}_plate")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(plate, check_existing=True)
    tex.extension = "EXTEND"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    ob.data.materials.append(mat)
    return None


def main():
    a = args()
    P = gather(a)
    if len(P) < 6:
        raise SystemExit(json.dumps({"error": f"only {len(P)} points; need 6 or more"}))
    extent = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    tol = a["tol"] or max(0.01, 0.02 * extent)
    planes, left = ransac_planes(P, a["planes"], tol, np.random.default_rng(a["seed"]))
    cam = bpy.context.scene.camera
    cam_pos = list(cam.matrix_world.translation) if cam else None
    out = []
    for i, (c, nrm, idx, rms) in enumerate(planes, 1):
        ob, size, n = make_wall(f"{a['name']}_{i}", c, nrm, P[idx], a["margin"], a["thickness"], cam_pos)
        warn = project_plate(ob, a["plate"], a["frame"]) if a["plate"] and a["frame"] is not None else None
        tilt = math.degrees(math.acos(min(1.0, abs(n[2]))))
        out.append({"object": ob.name, "points": int(len(idx)), "rms_mm": round(rms * 1000, 1),
                    "size_m": [round(size[0], 2), round(size[1], 2)], "normal": [round(x, 3) for x in n],
                    "kind": "floor" if tilt < 20 else ("wall" if tilt > 70 else "slope"), "warning": warn})
    res = {"planes": out, "unused_points": int(len(left)), "tolerance_m": round(tol, 3)}
    if not out:
        res["error"] = "no plane found; check the points or raise --tol"
    print(json.dumps(res, separators=(",", ":")))
    return res


RESULT = main()
