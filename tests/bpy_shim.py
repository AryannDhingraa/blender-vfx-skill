"""Makes the bpy Python module behave like `blender -b` for job tests:
-b [file.blend] --python-exit-code N -P script -o path -f frames -- args"""
import runpy
import sys
import traceback

import bpy

argv = sys.argv[1:]
extra = argv[argv.index("--") + 1:] if "--" in argv else []
argv = argv[:argv.index("--")] if "--" in argv else argv
exit_code = 0
i = 0
while i < len(argv):
    a = argv[i]
    if a == "--version":
        print(f"Blender {bpy.app.version_string} (bpy module)"); sys.exit(0)
    if a.endswith(".blend"):
        bpy.ops.wm.open_mainfile(filepath=a); i += 1
    elif a == "--python-exit-code":
        exit_code = int(argv[i + 1]); i += 2
    elif a == "-P":
        sys.argv = ["blender", "--"] + extra
        try:
            runpy.run_path(argv[i + 1], run_name="__main__")
        except SystemExit:
            pass
        except Exception:
            traceback.print_exc()
            sys.exit(exit_code)
        i += 2
    elif a == "-o":
        bpy.context.scene.render.filepath = argv[i + 1]; i += 2
    elif a == "-f":
        sc = bpy.context.scene
        for part in argv[i + 1].split(","):
            a0, _, b0 = part.partition("..")
            for f in range(int(a0), int(b0 or a0) + 1):
                sc.frame_set(f)
                target = sc.render.frame_path(frame=f)
                bpy.ops.render.render()
                bpy.data.images["Render Result"].save_render(filepath=target)
                print(f"Fra:{f} saved {target}")
        i += 2
    else:
        i += 1
