# Water interaction (splash, wake, something hitting water)

Strategy: 3D matchmove plus a local sim. Stages: 04, 07, 08, 09.

Steps:
1. Track; match the real water surface with an Ocean modifier or a plane.
2. Local liquid sim only around the interaction; blend its edges into the ocean surface.
3. Foam, spray and bubbles as their own sim or stock elements.
4. Wet surfaces after contact (Dynamic Paint wetmap).
5. Composite: match water colour and reflections, mist layer, grain.

Checks: sim edges invisible; splash scale matches the object's size and speed. Ocean-scale shots: use stock or a smaller idea.
