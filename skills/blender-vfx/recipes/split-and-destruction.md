# Splitting or destroying a real object

Strategy: 3D matchmove with the plate projected onto proxy geometry. Stages: 04, 05, 07, 08, 09.

Shoot: the object untouched, plus a clean plate of the background behind it.

Steps:
1. Track; model a rough proxy of the object; project the plate onto it from the tracked camera.
2. Cut with a Boolean or noise-displaced plane; shatter with Cell Fracture for breaking.
3. Animate or simulate the parts; add the hidden inside surfaces with a matching material.
4. Glowing hot edges and sparks for energy cuts; splinters and dust for wood and stone.
5. Paint out the original object where the pieces move away (clean plate, AI fill allowed if the user agrees).

Checks: projection does not smear as pieces turn; inside surfaces look like the material; background revealed behind matches the clean plate.
