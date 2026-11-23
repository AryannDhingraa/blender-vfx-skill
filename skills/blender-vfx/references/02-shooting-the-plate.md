# Shooting the plate

Real footage carries the realism. The CG only has to match it. Most failed VFX shots were lost on set.

## Before the shoot

- Gather reference: the shot you are copying, real footage of the event, photos of materials.
- Cut the shot list. Every shot doubles the VFX work. Start with the hardest shot.
- Decide per shot: 2D, 2.5D, 3D matchmove or full CG (`01-shot-brief.md`).

## Camera settings for VFX plates

- **Manual everything.** Fixed shutter, aperture, ISO, white balance (Kelvin, never auto), focus. Auto exposure or auto white balance changes mid-shot and breaks the composite.
- **Shutter.** Double the frame rate (1/50 for 24 or 25 fps). Where mains power is 50 Hz, 1/50 also avoids flicker from lights. Where it is 60 Hz, use 1/60.
- **Frame rate.** Pick one per project and keep it. 24 fps for a film look. Mixed frame rates cost hours later.
- **Resolution.** Shoot the highest uncropped mode. Check whether the camera crops at some frame rates; a crop changes the field of view and the tracking camera.
- **Stabilisation.** Off on a tripod. Handheld: optical (lens) stabilisation is fine; digital or "active" stabilisation crops and warps each frame differently, which breaks camera tracking. Turn it off and stabilise in post if needed.
- **Sharpening.** Turn in-camera sharpening (Detail) to its minimum. Sharpening halos hurt tracking, keying and roto.
- **Zoom lenses.** Never zoom during a VFX take. Use a repeatable position (fully wide or fully tele) so the focal length is known. Write it down or read it from the clip metadata.
- **Focus.** Manual focus on VFX shots. Autofocus hunting and focus breathing change the image scale.
- **Lens corrections.** Find out if distortion correction is forced on for the lens (it is on many kit zooms). If it is, the plate is already mostly undistorted; solve distortion in Blender only if the track error stays high.
- **Rolling shutter.** Many hybrid cameras skew fast motion, especially in 4K. Move the camera slowly on VFX shots, avoid whip pans, and match it in Cycles (Motion Blur, Rolling Shutter) if needed.

## Log profiles

- Log keeps highlight and shadow detail for grading. It is not required for VFX; a consistent, correctly exposed plate matters more.
- **8-bit cameras:** log spreads 8 bits thinly, so underexposure shows banding and noise fast. Expose 1 to 2 stops brighter than the log profile's nominal grey, protect highlights with zebras, and use ND filters to keep the shutter at 1/50 in daylight.
- **10-bit cameras:** log works as intended. Expose to the manufacturer's nominal grey or up to 1 stop over.
- **Do not change saturation, colour phase or colour depth inside a log profile.** Colour space transforms and LUTs assume the default profile. Do creative colour in the grade.
- Log raises the minimum ISO on most cameras, so bright scenes need ND.
- Turn on the camera's log viewing assist so you can judge exposure on set.

## Shoot extra for VFX

- **Clean plate.** Same framing and move with nobody in it.
- **Grey ball and chrome ball** (or a phone 360 photo) where the CG will stand, for lighting reference.
- **Colour chart or grey card** at the start of each setup.
- **Measurements.** Camera height, distance to the subject, one known distance on the ground for tracking scale.
- **Notes per shot:** focal length, frame rate, shutter, ISO, ND, sun direction.
- **Practical interaction.** Give actors something real: a prop hilt, a stand-in at the right height, a held object at the impact point to paint out later.
- **Fast action.** If it cannot be tracked at normal speed, shoot slow motion, do the VFX at that speed and speed it up at the end. Check if the slow motion mode crops.
- **Deliveries.** If the shot also goes out as 9:16, keep the action inside the centre 9:16 area of the 16:9 frame.
- Move bags, stands and crew out of frame. Every leftover is a paint-out.

## Camera notes to record in the profile

For the user's camera, record: bit depth, chroma subsampling, crop factor per mode, whether stabilisation is digital, whether distortion correction is forced, minimum ISO in log, and how bad the rolling shutter is. Look these up for the exact model; do not guess.
