# Splitting or destroying a real object

Strategy: 3D matchmove with the plate projected onto proxy geometry. Stages: 04, 05, 07, 08, 09.

Shoot: the object untouched, plus a clean plate of the background behind it.

Steps:
1. Track and solve. Turn the solve's points into a mesh (Clip editor: Reconstruction > 3D Markers to Mesh), then `scripts/build_proxy.py -- --object <mesh> --planes 2 --thickness 0.25 --plate <plate frame> --frame <F>` fits walls and floors to the points and bakes the plate projection into UVs. Check `rms_mm` (under about 20 at 1080p) before trusting a plane.
2. Break only what is hit: `scripts/destruction.py -- --object proxy_1 --impact x,y,z --radius 0.6 --pieces 24 --frame <impact> --end <F> --ground proxy_2`. The rest of the wall stays one static object. `volume_ok` must be true. Bake with `--bake` only after asking if the estimate is long; render through `vfx.py run`.
3. Animate or simulate the parts; add the hidden inside surfaces with a matching material.
4. Glowing hot edges and sparks for energy cuts; splinters and dust for wood and stone.
5. Paint out the original object where the pieces move away (clean plate, AI fill allowed if the user agrees).

Checks: projection does not smear as pieces turn; inside surfaces look like the material; background revealed behind matches the clean plate.
