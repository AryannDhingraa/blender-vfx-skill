# Finishing and delivery

## Grade and sound

- Bring the VFX renders back into the grading app, apply the colour transform from `03-color-pipeline.md`, then grade the whole sequence together so shots match.
- Sound sells half the effect: impacts timed to the frame, footsteps, whooshes, ambience, room tone. Use licensed libraries only.
- Show the cut to someone with fresh eyes. Fix what they flag.

## One shoot, two shapes

- 16:9 is the master. For 9:16, keep the action in the centre 9:16 area when shooting, render CG for the full 16:9 frame, and reframe in the edit.
- Check every VFX shot in both crops. Giveaways hide at the edges of one and the centre of the other.

## Masters and exports

| Destination | Export |
| --- | --- |
| Archive master | ProRes 422 HQ (or DNxHR HQX), full resolution |
| YouTube | H.264 or H.265 at the timeline resolution, high bitrate |
| Reels, TikTok, Shorts | 1080x1920, H.264 |
| Festivals | Follow each festival's spec; usually a ProRes master or a DCP made with DCP-o-matic |

## Asset and rights check

- Every asset, sound, music track and font is in `asset-licenses.md` with its licence.
- Festivals and paid work need commercial rights for everything, software included (some free editions forbid commercial use).
- No real brand logos or recognisable people without permission.

## Final verification

Run `12-review-checklist.md`, then check the exported file: frame count (seconds times fps), resolution, duration, audio present, no black or duplicated frames. `vfx.py verify FILE --fps N --seconds N` does this with ffprobe.
