# Setup interview (run once)

Ask these in rounds of up to 4, with options. Skip anything the user already told you. Save the answers to `vfx-profile.md` using `templates/vfx-profile.md`. After that, read the profile instead of asking again. Re-ask only if the user says their gear changed.

## Round 1: what they make

1. What are you making? (short films, YouTube videos, social reels, music videos, client work, learning)
2. Where will it be shown? (YouTube 16:9, Reels/TikTok/Shorts 9:16, festivals or cinema, client delivery). Several allowed.
3. Experience with Blender? (new, some, comfortable, pro)
4. How hands-on do you want to be? (do it all for me and ask at gates, explain as you go, teach me step by step)

## Round 2: camera and lens

1. Camera make and model (exact model matters: 8-bit vs 10-bit, rolling shutter, crop modes).
2. Picture profile you shoot in (standard, S-Log2, S-Log3, V-Log, C-Log, N-Log, HLG, a cine profile, RAW). Ask for any changes they make to it (saturation, colour phase, detail, black level).
3. Resolution and frame rate you usually record.
4. Lenses: zoom or prime, focal lengths, whether lens corrections are forced on in camera.

## Round 3: computers

1. Main computer: OS, CPU, GPU (model and VRAM), RAM, free disk space.
2. Any second computer that could render or bake overnight?
3. External or network storage for caches and renders?
4. Longest render or bake they will accept without being asked (default 10 minutes).

## Round 4: software

1. Blender version.
2. Grading and editing app, and edition (DaVinci Resolve Free or Studio, Premiere, Final Cut, other).
3. Other tools they own (Nuke, After Effects, Houdini, FLIP Fluids, motion capture suit, Mixamo, tracking software).
4. Asset budget: free only, small purchases fine, or will hire help.

## Round 5: style and limits (optional)

1. Reference films or creators whose look they want.
2. Anything to avoid (gore, real brands, particular looks).
3. Do they need commercial rights for everything (client work, festivals)? This decides which assets and software licences are allowed.

## After the interview

Write the profile. Then derive and add to it:

- Hardware tier from `references/11-hardware.md`.
- Camera notes from `references/02-shooting-the-plate.md` (bit depth, log handling, stabilisation, zoom rules).
- Colour round trip choice from `references/03-color-pipeline.md`.
- Automation options: what the grading app allows (for example, Resolve Free does not allow external Python scripting in recent versions; Studio does).

Read the profile back to the user in 5 to 8 lines and ask them to confirm.
