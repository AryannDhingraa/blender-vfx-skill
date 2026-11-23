# Colour pipeline

Goal: the plate goes into Blender and comes back out looking identical, so only the CG changes. Test this before any VFX work.

## Pick a round trip

**A. Linear EXR (best).** In the grading app, use a colour space transform to change only the gamma from the camera's log curve to Linear, and export a half-float EXR sequence (check your grading app's edition can export EXR; if not, use B). In Blender, load it as the matching linear camera gamut. Blender 5.x ships linear versions of the common camera gamuts (for example Linear S-Gamut3.Cine, Linear ARRI Wide Gamut 4, Linear V-Gamut, Linear DaVinci WideGamut). If yours is missing, convert to Linear Rec.709 primaries in the grading app instead. CG and plate then share one linear space with highlight headroom.

**B. Display-referred (simplest).** Convert the log plate to Rec.709 (gamma 2.4) and export a 16-bit TIFF sequence or ProRes 422 HQ. In Blender, load it as Rec.1886 (or sRGB if that matches better). Highlights above white clip, but it is reliable and fine for 8-bit sources.

**C. Original log.** Only if your Blender OCIO config includes the camera's log space. Most stock configs do not.

Use the same transform settings for every shot in a project. Write the choice in the profile.

## Blender settings

- Compositing CG over footage: View Transform **Standard**, so the plate displays as it came in. Do the look in the grade later.
- Full CG shots with no plate: View Transform **AgX**.
- Exposure in Colour Management, never by scaling every light.
- Render output: multilayer OpenEXR, half float, scene linear.

## The round trip test (do it once per project)

1. Load one plate into Blender.
2. Composite it with no CG and render a few frames.
3. Put the render over the original in the grading app with Difference blend mode.
4. It should be black. If not, fix the colour space settings before going further.

## Grading back

After the VFX render returns, apply the matching transform (linear to Rec.709, or the camera's LUT), then the creative grade, on the whole sequence together.

## 8-bit log warning

8-bit log has little room. Do not push the grade hard on 8-bit sources, and add grain after grading to hide banding.
