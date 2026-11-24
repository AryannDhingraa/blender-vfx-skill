# Test shots for the benchmark

Twenty short clips (5 to 10 seconds each) that every change to the skill and engine is tested against. Film them once, keep them forever. Note camera, lens, focal length, frame rate and shutter for each.

| # | Shot | Tests |
| --- | --- | --- |
| 1 | Locked tripod, desk | 2D tracking, no solve |
| 2 | Tripod pan across a room | Tripod solve |
| 3 | Slow handheld push toward a table | Basic parallax solve |
| 4 | Walking past a wall with posters | Full solve, lots of features |
| 5 | Walking past a plain white wall | Low texture |
| 6 | Handheld in low light | Noise, weak features |
| 7 | Someone walks through frame | Moving objects in the tracks |
| 8 | Fast whip pan | Motion blur |
| 9 | Fast handheld run | Blur and rolling shutter |
| 10 | Zoom in during the shot | Changing focal length |
| 11 | Shiny car or glass | Reflections fooling the tracker |
| 12 | Trees moving in wind | Unstable features |
| 13 | Drone orbit | Big parallax, distant features |
| 14 | Camera behind a passing pole | Occluded tracks |
| 15 | Phone footage | Different lens and stabilisation |
| 16 | Person standing, room behind | Masking and holdouts |
| 17 | Hand holding a prop | Object tracking |
| 18 | Floor with a mark where CG will stand | Contact and shadows |
| 19 | Window with bright sky | Clipped highlights, sky replacement |
| 20 | Night street with lights | Practical light matching |

For each shot the benchmark records: `analyse_footage.py` result, solve error and `track_report.py` flags, render time, and a human 1 to 5 rating of the final comp.
