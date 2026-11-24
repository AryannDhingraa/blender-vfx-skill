"""Stands in for the blender executable in job tests (no Blender needed).
Understands: -b [file] --python-exit-code N -P script -o pattern -f frames -- args
Env: FAKE_CRASH_AT=n (write a broken frame n, exit 1), FAKE_SLEEP=s per frame,
FAKE_BLACK=n (frame n black), FAKE_LOG=path (append rendered frames)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import make_png  # noqa: E402

argv = sys.argv[1:]
if "--" in argv:
    argv = argv[:argv.index("--")]
out, frames = None, []
i = 0
while i < len(argv):
    if argv[i] == "-o":
        out = argv[i + 1]; i += 2
    elif argv[i] == "-f":
        for part in argv[i + 1].split(","):
            if ".." in part:
                a, b = part.split("..")
                frames += list(range(int(a), int(b) + 1))
            else:
                frames.append(int(part))
        i += 2
    else:
        i += 1
crash = int(os.environ.get("FAKE_CRASH_AT", "-1"))
black = int(os.environ.get("FAKE_BLACK", "-1"))
for f in frames:
    path = out.replace("####", f"{f:04d}") + ".png"
    if f == crash:
        make_png(path, value=100)
        with open(path, "r+b") as fh:
            fh.truncate(40)
        print(f"Error: render crashed on frame {f}")
        sys.exit(1)
    make_png(path, value=1 if f == black else 120)
    if os.environ.get("FAKE_LOG"):
        with open(os.environ["FAKE_LOG"], "a") as fh:
            fh.write(f"{f}\n")
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
print("Blender quit")
