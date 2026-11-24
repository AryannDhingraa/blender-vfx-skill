# Assets and materials

## Sourcing

1. Search free CC0 libraries first: `vfx.py assets search "<words>" --type model|texture|hdri --sheet _review/assets.jpg`. It ranks Poly Haven and ambientCG results for the shot and this machine (polycount, texture size, real size) and makes one contact sheet. Show the user the sheet and the 3 to 5 options (name, link, licence, resolution, polygons, suitability), wait for their pick and resolution, then `vfx.py assets download ID --source ... --type ... --res 2k --dest 04_assets --approved --licence-log 00_brief/asset-licenses.md`, then `scripts/import_asset.py -- --manifest 04_assets/ID/asset.json`.
   Nothing fits: offer `scripts/procedural_asset.py -- --kind rock|debris|crate|brick_wall|plank --preview _review/asset.png` and show the preview before using it.
2. Then paid stores. Ask before buying. Log every asset in `asset-licenses.md` (template in `templates/`) with source, licence and whether it allows commercial use.
3. Missing model: generate a reference image described like an expert would (exact type, shape, silhouette details, with exclusions like no text, no logos), turn it into a mesh with an image to 3D tool, keep the shape, delete its textures, remesh or retopologise, unwrap.
4. Sculpting a hero creature from scratch takes months. Buy or commission instead.

## Import checks

- Scale against the 1.75 m human reference. Apply scale.
- Face Orientation overlay all blue. Select Non Manifold for holes.
- A model that loads black, inside out or broken is not used until fixed.
- Pick models with the parts you will show (an interior if it gets cut open).

## Materials

- Scanned PBR sets. Base colour sRGB, all other maps Non-Color. OpenGL normal maps.
- Upgrade every downloaded model: a roughness map against the plastic look, a displacement map for close ups (Displacement and Bump on a subdivided mesh).
- Roughness never one flat value. Add smudges, wear, dirt where hands and weather touch.
- Metalness is 0 or 1.
- Break tiling: vary scale and rotation, blend a second texture through a noise mask.
- Match texture scale to the real size of the object.
- Bevel hard edges (1 to 5 mm on props) with Harden Normals.

## Digital doubles

- Image to 3D model of the actor, the actor's photo projected as texture, a downloaded clothing model simulated with cloth.
- Keep doubles small in frame, in motion blur, or partly hidden. Close ups need a proper scan.

## Rigging

- Armature plus weight painting, or an auto-rig tool. Humanoids can use Mixamo or a mocap tool's retargeting.
