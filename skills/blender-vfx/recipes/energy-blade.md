# Energy blade (saber style)

Strategy: 2D when it only glows; 3D when it cuts or lights CG. Stages: 04, 09 (3D also 08).

Shoot: a real hilt, ideally with a bright stick or tape on the blade for tracking. Darker scenes make the glow read stronger.

2D steps:
1. Track the hilt base and tip per frame (2D tracks or hand keys).
2. Draw the blade shape between them: white core, coloured glow layers, slight flicker.
3. Motion blur matched to the swing; stretch the blade on fast swings.
4. Interactive light on the actor and ground in the blade colour.

3D extras: object track the hilt, parent a blade mesh with emission, boolean cuts on whatever it hits, sparks at contact, render the light it throws on CG.

Checks: blade stays attached at the hilt every frame; glow light flickers with the blade.
