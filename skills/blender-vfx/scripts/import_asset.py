"""Bring a downloaded asset (from `vfx.py assets download`) into the scene.

  blender -b shot.blend -P import_asset.py -- --manifest 04_assets/barrel_01/asset.json \
      [--object Wall] [--location 0,2,0] [--rotate 120] [--strength 1.0]

model    imports the glTF, reports real size, polygons and texture memory
texture  builds a PBR material (colour sRGB, data maps Non-Color) and assigns it to --object
hdri     sets the world to the HDRI, rotated by --rotate degrees
Prints one JSON line. Nothing is saved; save a new .blend version after checking.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"manifest": None, "object": None, "location": None, "rotate": "0", "strength": "1.0"}
    for i in range(0, len(argv) - 1):
        k = argv[i].lstrip("-")
        if argv[i].startswith("--") and k in a:
            a[k] = argv[i + 1]
    return a


def tex_node(nt, path, data):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path, check_existing=True)
    if data:
        n.image.colorspace_settings.is_data = True
    return n


def material_from(m, root):
    mat = bpy.data.materials.new(m["id"])
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    f = {k: os.path.join(root, v) for k, v in m["files"].items()}
    if "diffuse" in f:
        nt.links.new(tex_node(nt, f["diffuse"], False).outputs["Color"], b.inputs["Base Color"])
    if "roughness" in f:
        nt.links.new(tex_node(nt, f["roughness"], True).outputs["Color"], b.inputs["Roughness"])
    elif "arm" in f:
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tex_node(nt, f["arm"], True).outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs[1], b.inputs["Roughness"])
        nt.links.new(sep.outputs[2], b.inputs["Metallic"])
    if "metallic" in f:
        nt.links.new(tex_node(nt, f["metallic"], True).outputs["Color"], b.inputs["Metallic"])
    if "normal" in f:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(tex_node(nt, f["normal"], True).outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    if "displacement" in f:
        disp = nt.nodes.new("ShaderNodeDisplacement")
        disp.inputs["Scale"].default_value = 0.02
        nt.links.new(tex_node(nt, f["displacement"], True).outputs["Color"], disp.inputs["Height"])
        nt.links.new(disp.outputs["Displacement"], nt.nodes["Material Output"].inputs["Displacement"])
    return mat


def tex_mb(images):
    return round(sum(i.size[0] * i.size[1] * 4 for i in images if i.size[0]) / 2 ** 20, 1)


def main():
    a = args()
    with open(a["manifest"]) as fh:
        m = json.load(fh)
    root = os.path.dirname(os.path.abspath(a["manifest"]))
    res = {"asset": m["id"], "type": m["type"], "licence": m.get("licence")}
    if m["type"] == "model":
        before = set(bpy.data.objects)
        imgs_before = set(bpy.data.images)
        bpy.ops.import_scene.gltf(filepath=os.path.join(root, m["files"]["model"]))
        new = [o for o in bpy.data.objects if o not in before]
        if a["location"]:
            loc = Vector([float(x) for x in a["location"].split(",")])
            for o in new:
                if o.parent is None:
                    o.location += loc
        meshes = [o for o in new if o.type == "MESH"]
        dg = bpy.context.evaluated_depsgraph_get()
        polys = sum(len(o.evaluated_get(dg).data.polygons) for o in meshes)
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        size = [round(max(p[i] for p in pts) - min(p[i] for p in pts), 3) for i in range(3)] if pts else None
        res.update({"objects": [o.name for o in new], "polygons": polys, "size_m": size,
                    "texture_mb": tex_mb([i for i in bpy.data.images if i not in imgs_before])})
        if size and (max(size) > 50 or max(size) < 0.01):
            res["warning"] = "size looks wrong for real meters; check the scale before use"
    elif m["type"] == "texture":
        mat = material_from(m, root)
        res["material"] = mat.name
        if a["object"]:
            ob = bpy.data.objects[a["object"]]
            if ob.data.materials:
                ob.data.materials[0] = mat
            else:
                ob.data.materials.append(mat)
            res["assigned_to"] = ob.name
            if not ob.data.uv_layers:
                res["warning"] = "object has no UVs; unwrap it or use box projection"
        res["texture_mb"] = tex_mb([n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"])
    elif m["type"] == "hdri":
        sc = bpy.context.scene
        w = sc.world or bpy.data.worlds.new("World")
        sc.world = w
        if w.node_tree is None:
            w.use_nodes = True
        nt = w.node_tree
        bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None) or nt.nodes.new("ShaderNodeBackground")
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(os.path.join(root, m["files"]["hdri"]), check_existing=True)
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value[2] = math.radians(float(a["rotate"]))
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = float(a["strength"])
        out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
        nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
        res.update({"world": w.name, "rotation_deg": float(a["rotate"]), "image": list(env.image.size)})
    print(json.dumps(res, separators=(",", ":")))
    return res


RESULT = main()
