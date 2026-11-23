# Animation

- Reference first. Film yourself acting the shot, or find real footage. Match key poses to it.
- Humans and humanoids: motion capture (suit, video based mocap, or Mixamo stock moves), retargeted to the character's skeleton.
- Creatures: keyframe animation, then secondary motion: shake on impacts, muscle jiggle, breathing, tail and skin follow-through. Weight comes from timing; heavy things accelerate slowly and stop hard.
- Stunts: track the plate, match the actor's poses on key frames, hand off to the double for the impossible part.
- Rolling objects: a driver ties rotation to position (rotation = distance travelled / radius) so nothing slides.
- Props in hands: parent to the hand bone, then fix contact frames by hand.
- Camera moves for full CG: ease in and out (Bezier, never Linear), slow, with a little handheld noise if the rest of the film is handheld.
- Physics-driven motion (falls, crashes, throws) is simulated, not keyed: see `07-simulation.md`.
- Check animation against the plate at full speed, not frame by frame. Then scrub contact frames for sliding.
