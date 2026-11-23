# Simulation

If physics decides the motion, simulate it. Expect many attempts. Ask before any bake over the user's time limit.

## Budget first

- Doubling simulation resolution means about 8 times the voxels and time. Iterate at low resolution, run one high resolution bake when the motion is approved.
- Bake to a fast drive with plenty of space. Caches get huge.
- Anything huge or far away (big explosions, distant smoke, rain, dust plumes): use stock elements composited in. Simulate only what touches the CG or the actor.
- Split big effects into several sims by distance to camera so close ones get the resolution.

## Rigid bodies and destruction

- Simulate a low resolution proxy, then swap the high resolution model back to follow it.
- Control with setup, not keys: gravity off until the fall, an initial velocity for a throw, a force that switches on mid-sim, a temporary soft collider (a pit of small spheres) deleted after the bake.
- Cuts: Boolean modifier. Shatter: the Cell Fracture extension. Crack growth: Geometry Nodes. Hot cut edges glow; add sparks.
- Change one setting per attempt and note it in `shot-log.md`.

## Smoke, fire, explosions (Mantaflow)

- Fire needs fuel and heat: Flow type Fire + Smoke with fuel and temperature.
- Explosion: emit particles outward fast from the blast point, use them as the flow source with Initial Velocity on.
- Moving objects are colliders and pass velocity into the smoke, so it wraps around them.
- Portals and vortices: a noisy torus source, a Vortex field, a negative Force field to pull inward, a Turbulence field.
- More layers read as more real: trails, debris, dust, secondary smoke.
- Render volumes in their own View Layer.

## Water

- Mantaflow liquid is built in. The FLIP Fluids add-on (paid) is closer to film tools and includes whitewater.
- Foam, spray and bubbles are their own simulation and render.
- Blend a local sim's edges into an Ocean modifier surface with matching displacement.
- Thick liquids: raise viscosity. Wet ground where liquid passed: Dynamic Paint wetmap.

## Cloth and soft body

- Clothing and flags: cloth. Squashing and rolling soft objects: soft body on a low resolution proxy.

## Determinism

Fixed seeds, frame-driven time, bake everything before final render. Never render a sim live.

## Know the limit

Ocean scale water and city scale explosions are Houdini territory. Say so and offer the stock element or 2.5D version instead of a weak full sim.
