# Lessons

What worked and what failed on real shots. The agent reads this before planning a new shot and adds 1 to 3 lines after each finished shot. Keep it under 60 lines; merge repeats.

## Shot records (one line per finished shot)
Format: shot | footage and camera | solve error | render engine, samples, time per frame | what looked wrong | fix that worked
- (example) SHOT010 | handheld, 4K 24p, 16 mm | 0.21 px | Cycles 0.03 / 512, 39 s | CG too clean | grain 0.008 matched the plate

## Settings that worked
- (example) Cycles 0.03 threshold + OIDN was clean enough for a dusk exterior at 1080p.

## Mistakes not to repeat
- (example) Forgot to set the clip sensor width; the solve bent the floor.

## User preferences found along the way
- (example) Wants previews at 50 percent, finals only after a contact sheet.
