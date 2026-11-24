"""Tests that run real Blender (the bpy module). Skipped when bpy is not installed."""
import json
import os
import sys

import pytest

from conftest import ROOT, SCRIPTS, bpy_python, make_png, needs_bpy, run_blender

pytestmark = needs_bpy

PRE = f"""
import sys, json, runpy
sys.path.insert(0, {SCRIPTS!r})
import bpy
def run(name, *args):
    sys.argv = ['blender', '--', *map(str, args)]
    return runpy.run_path({SCRIPTS!r} + '/' + name, run_name='__main__')
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
"""


def _last_json(out):
    return json.loads([l for l in out.splitlines() if l.startswith(("{", "["))][-1])


def test_projection_matches_blender_camera():
    out = run_blender(PRE + """
import numpy as np, math
from bpy_extras.object_utils import world_to_camera_view
from vfxlib import trackmath as tm
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.sensor_fit = 'HORIZONTAL'; cam.data.sensor_width = 23.5; cam.data.lens = 16
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
cam.location = (1.2, -4.0, 1.6); cam.rotation_euler = (math.radians(82), math.radians(3), math.radians(14))
bpy.context.view_layer.update()
rng = np.random.default_rng(0); worst = 0
f = cam.data.lens / cam.data.sensor_width * 1920
for _ in range(50):
    X = np.array([rng.uniform(-2, 3), rng.uniform(1, 8), rng.uniform(0, 3)])
    v = world_to_camera_view(sc, cam, __import__('mathutils').Vector(X))
    if v.z <= 0: continue
    want = np.array([v.x * 1920, (1 - v.y) * 1080])
    got = tm.project(X, np.array(cam.matrix_world), f, 960, 540)[0][0]
    worst = max(worst, float(np.abs(got - want).max()))
print(json.dumps({'worst_px': worst}))
""")
    assert _last_json(out)["worst_px"] < 1e-3


def test_track_report_unsolved_and_holdout_prep(tmp_path):
    for i in range(1, 21):
        make_png(str(tmp_path / f"plate_{i:04d}.png"), 64, 36, 100)
    out = run_blender(PRE + f"""
clip = bpy.data.movieclips.load({str(tmp_path / 'plate_0001.png')!r})
import itertools
for n, (x, y) in enumerate(itertools.product([0.15, 0.5, 0.85], [0.2, 0.5, 0.8])):
    t = clip.tracking.tracks.new(name=f't{{n}}', frame=1)
    for f in range(1, 21):
        t.markers.insert_frame(f, co=(x + 0.001 * f, y))
r = run('track_report.py')['REPORT'][0]
p = run('track_report.py', '--prepare-holdout', 3)['REPORT'][0]
w = sorted(t.name for t in clip.tracking.tracks if t.weight == 0)
q = run('track_report.py', '--restore-holdout')['REPORT'][0]
print(json.dumps({{'r': r, 'p': p, 'w': w, 'q': q}}))
""")
    d = _last_json(out)
    r = d["r"]
    assert r["solve_valid"] is False and r["trust"] == "low" and r["min_tracks_per_frame"] == 9
    assert any("no valid camera solve" in f for f in r["flags"]) and r["tracks"] == 9
    assert len(d["p"]["holdout_tracks"]) == 3 and d["w"] == sorted(d["p"]["holdout_tracks"])
    assert d["q"]["restored"] == 3


def test_proxy_and_partial_destruction(tmp_path):
    out = run_blender(PRE + f"""
import numpy as np, math
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -2, 1.5); cam.rotation_euler = (math.radians(90), 0, 0)
rng = np.random.default_rng(0)
wall = np.column_stack([rng.uniform(-2, 2, 40), 3 + rng.normal(0, .005, 40), rng.uniform(0, 2.5, 40)])
floor = np.column_stack([rng.uniform(-2, 2, 30), rng.uniform(0, 3, 30), rng.normal(0, .005, 30)])
json.dump(np.vstack([wall, floor, rng.uniform(-2, 2, (5, 3))]).tolist(), open({str(tmp_path / 'p.json')!r}, 'w'))
img = bpy.data.images.new('plate', 32, 18); img.filepath_raw = {str(tmp_path / 'plate.png')!r}; img.file_format = 'PNG'; img.save()
pr = run('build_proxy.py', '--points', {str(tmp_path / 'p.json')!r}, '--planes', 2, '--thickness', 0.25,
         '--plate', {str(tmp_path / 'plate.png')!r}, '--frame', 1)['RESULT']
w = [p for p in pr['planes'] if p['kind'] == 'wall'][0]
fl = [p for p in pr['planes'] if p['kind'] == 'floor'][0]
d = run('destruction.py', '--object', w['object'], '--impact', '0,3,1.2', '--radius', .6, '--pieces', 16,
        '--frame', 5, '--end', 40, '--ground', fl['object'])['RESULT']
pieces = [o for o in bpy.data.objects if '_piece_' in o.name]
start = {{o.name: o.matrix_world.translation.copy() for o in pieces}}
for f in range(1, 41): sc.frame_set(f)
moved = sum((o.matrix_world.translation - start[o.name]).length > 0.05 for o in pieces)
before = sum((o.matrix_world.translation - start[o.name]).length > 1e-4 for o in pieces if False)
sc.frame_set(4)
early = sum((o.matrix_world.translation - start[o.name]).length > 1e-3 for o in pieces)
print(json.dumps({{'proxy': pr, 'destr': d, 'moved': int(moved), 'early': int(early),
                  'uv': [l.name for l in bpy.data.objects[w['object']].data.uv_layers]}}))
""")
    d = _last_json(out)
    w = [p for p in d["proxy"]["planes"] if p["kind"] == "wall"][0]
    assert w["rms_mm"] < 10 and abs(w["normal"][1]) > 0.99 and d["uv"] == ["projection"]
    assert d["destr"]["pieces"] == 16 and d["destr"]["volume_ok"]
    assert d["moved"] >= 12, "most pieces should fly"
    assert d["early"] == 0, "nothing may move before the impact frame"


def test_procedural_assets_and_preview_restores_settings(tmp_path):
    out = run_blender(PRE + f"""
sc.render.resolution_x = 1234; sc.render.engine = 'BLENDER_EEVEE' if 'BLENDER_EEVEE' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else sc.render.engine
eng = sc.render.engine
r = run('procedural_asset.py', '--kind', 'rock', '--size', .4, '--preview', {str(tmp_path / 'rock.png')!r})['RESULT']
kinds = {{k: run('procedural_asset.py', '--kind', k, '--size', 1.0, '--count', 4)['RESULT'] for k in ('crate', 'brick_wall', 'plank', 'debris')}}
print(json.dumps({{'rock': r, 'kinds': kinds, 'res_x': sc.render.resolution_x, 'engine_back': sc.render.engine == eng,
                  'leftovers': [o.name for o in bpy.data.objects if 'preview' in o.name]}}))
""")
    d = _last_json(out)
    assert os.path.getsize(d["rock"]["preview"]) > 1000 and d["res_x"] == 1234 and d["engine_back"]
    assert not d["leftovers"]
    assert 0.2 < max(d["rock"]["size_m"]) < 0.6
    assert d["kinds"]["debris"]["objects"] and d["kinds"]["crate"]["size_m"] == [1.0, 1.0, 1.0]


def test_import_assets_from_local_downloads(tmp_path):
    a = tmp_path / "assets"
    out = run_blender(PRE + f"""
import os
os.makedirs({str(a / 'box')!r}); os.makedirs({str(a / 'tex')!r}); os.makedirs({str(a / 'sky')!r})
bpy.ops.mesh.primitive_cube_add(size=0.5)
bpy.ops.export_scene.gltf(filepath={str(a / 'box' / 'box.gltf')!r}, export_format='GLTF_SEPARATE')
bpy.ops.wm.read_factory_settings(use_empty=True)
json.dump({{'id': 'box', 'type': 'model', 'licence': 'CC0', 'files': {{'model': 'box.gltf'}}}}, open({str(a / 'box' / 'asset.json')!r}, 'w'))
for n in ('diff', 'rough', 'nor'):
    im = bpy.data.images.new(n, 8, 8); im.filepath_raw = {str(a / 'tex')!r} + f'/{{n}}.png'; im.file_format = 'PNG'; im.save()
json.dump({{'id': 'tex', 'type': 'texture', 'licence': 'CC0', 'files': {{'diffuse': 'diff.png', 'roughness': 'rough.png', 'normal': 'nor.png'}}}}, open({str(a / 'tex' / 'asset.json')!r}, 'w'))
im = bpy.data.images.new('sky', 16, 8, float_buffer=True); im.filepath_raw = {str(a / 'sky' / 'sky.exr')!r}; im.file_format = 'OPEN_EXR'; im.save()
json.dump({{'id': 'sky', 'type': 'hdri', 'licence': 'CC0', 'files': {{'hdri': 'sky.exr'}}}}, open({str(a / 'sky' / 'asset.json')!r}, 'w'))
bpy.ops.mesh.primitive_plane_add(); bpy.context.active_object.name = 'Wall'
import os
m = run('import_asset.py', '--manifest', {str(a / 'box' / 'asset.json')!r}, '--location', '1,0,0')['RESULT']
t = run('import_asset.py', '--manifest', {str(a / 'tex' / 'asset.json')!r}, '--object', 'Wall')['RESULT']
h = run('import_asset.py', '--manifest', {str(a / 'sky' / 'asset.json')!r}, '--rotate', 90)['RESULT']
mat = bpy.data.materials['tex']
cs = {{os.path.basename(n.image.filepath): n.image.colorspace_settings.is_data for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE'}}
print(json.dumps({{'m': m, 't': t, 'h': h, 'cs': cs}}))
""")
    d = _last_json(out)
    assert d["m"]["size_m"] == [0.5, 0.5, 0.5] and d["m"]["polygons"] in (6, 12)  # glTF may triangulate
    assert d["t"]["assigned_to"] == "Wall" and d["cs"]["diff.png"] is False and d["cs"]["rough.png"] is True
    assert d["h"]["rotation_deg"] == 90 and d["h"]["image"] == [16, 8]
    from vfxlib.frames import check_file
    assert check_file(str(a / "sky" / "sky.exr")) is None  # our EXR check accepts Blender's own EXR


def test_setup_probe_doctor_contact(tmp_path):
    root = tmp_path / "film"
    out = run_blender(PRE + f"""
import os
s = run('setup_shot.py', '--root', {str(root)!r}, '--shot', 'SH010', '--fps', 25, '--res', '640x360',
        '--sensor', 23.5, '--focal', 16, '--tier', 'cpu')
bpy.ops.mesh.primitive_cube_add()
p = run('probe_scene.py')['PROBE']
dr = run('render_doctor.py')
sc.frame_end = 3; sc.cycles.samples = 2
c = run('contact_sheet.py', '--frames', '1,2,3', '--pct', 10, '--samples', 2)
print(json.dumps({{'saved': [f for f in os.listdir({str(root / '05_blend' / 'SH010')!r})], 'probe': p if isinstance(p, dict) else json.loads(p)}}))
""")
    d = _last_json(out)
    assert any(f.endswith("_v001.blend") for f in d["saved"])
    for folder in ("00_brief", "02_plates", "07_renders", "_review", "_tmp"):
        assert (root / folder).is_dir()
    assert (root / "_review" / "contact").is_dir() and len(list((root / "_review" / "contact").glob("*.png"))) >= 3


def test_real_render_job_with_corrupt_frame_resume(tmp_path):
    from vfxlib import jobs
    blend = str(tmp_path / "shot.blend")
    run_blender(PRE + f"""
bpy.ops.mesh.primitive_cube_add(); bpy.ops.object.light_add(type='SUN')
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (5, -5, 4); cam.rotation_euler = (1.0, 0, 0.785)
sc.render.engine = 'CYCLES'; sc.cycles.samples = 1; sc.cycles.device = 'CPU'
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 96, 54, 100
if hasattr(sc.render.image_settings, 'media_type'):
    sc.render.image_settings.media_type = 'MULTI_LAYER_IMAGE'
else:
    sc.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
bpy.ops.wm.save_as_mainfile(filepath={blend!r})
""")
    shim = os.path.join(ROOT, "tests", "bpy_shim.py")
    jd, ld = str(tmp_path / "jobs"), str(tmp_path / "logs")
    pattern = str(tmp_path / "renders" / "####.exr")
    r = jobs.run("render", jd, ld, blend=blend, blender=f"{bpy_python()}|{shim}", timeout=600, frames="1-4",
                 pattern=pattern, output=str(tmp_path / "renders" / "####"), pixels=False)
    assert r["status"] == "success", r
    with open(tmp_path / "renders" / "0003.exr", "r+b") as f:
        f.truncate(os.path.getsize(tmp_path / "renders" / "0003.exr") // 2)
    s = jobs.status(jd, "render")
    assert s["status"] == "success"
    from vfxlib.frames import verify_sequence
    v = verify_sequence(pattern, 1, 4, pixels=False)
    assert v["rerender"] == "3" and "truncated" in list(v["corrupt"].values())[0]
    m = json.load(open(os.path.join(jd, "render.json")))
    m["status"] = "incomplete"
    json.dump(m, open(os.path.join(jd, "render.json"), "w"))
    r2 = jobs.resume("render", jd, ld)
    assert r2["status"] == "success" and r2["attempt"] == 2
    assert verify_sequence(pattern, 1, 4, pixels=False)["status"] == "ok"
