# Vehicle, ship or aircraft flyby

Strategy: 3D matchmove. Stages: 04, 05, 06, 08, 09.

Steps:
1. Track; model rough ground.
2. Downloaded model with upgraded shaders (roughness variation, panel wear).
3. Path along a curve with banking on turns; speed reads from size and motion blur.
4. Heat haze, dust trail or contrails where the environment supports them.
5. Composite: atmosphere fade with distance, motion blur, camera shake as it passes close, sound doppler in the edit.

Checks: scale reads (a ship far away is soft and low contrast); motion blur matches the plate shutter.
