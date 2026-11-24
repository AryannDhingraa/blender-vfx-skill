#!/usr/bin/env python3
"""Small, recoverable state for one shot. Plain Python, no Blender needed.

The agent reads `show` (a few lines) instead of re-checking the whole project.
Files live next to the shot's scenes, in <shot_dir>/state/:
  state.json        current state, kept under MAX_BYTES (paths, not data)
  state.json.bak    previous good copy
  history.jsonl     append-only log of every change, used only to recover

Commands (all print one short result):
  init    DIR --shot NAME [--mode filmmaker|vfx-artist]
  show    DIR                       compact summary, last 3 events
  set     DIR key=value [...]       dotted keys, values parsed as JSON when possible
  done    DIR STAGE [--note TEXT]   mark a stage complete, set the next one
  result  DIR NAME PATH             record a reusable output (size and mtime kept)
  check   DIR NAME                  is a recorded output still valid?
  recover DIR                       rebuild state.json from history, else the backup
"""
import argparse, json, os, sys, time
from collections import deque

MAX_BYTES = 4096
STAGES = ["brief", "plate", "analyse", "track", "build", "light", "preview",
          "render", "comp", "review", "deliver"]


def paths(d):
    s = os.path.join(d, "state")
    return s, os.path.join(s, "state.json"), os.path.join(s, "state.json.bak"), os.path.join(s, "history.jsonl")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def load(d, report=None):
    _, cur, bak, _ = paths(d)
    for p in (cur, bak):
        try:
            with open(p) as f:
                st = json.load(f)
            if report is not None and p == bak:
                report.append("WARNING state.json unreadable, showing backup. Run `recover`.")
            return st
        except (OSError, ValueError):
            continue
    return None


def last_history(hist):
    last = None
    try:
        with open(hist) as f:
            for line in f:
                try:
                    last = json.loads(line)
                except ValueError:
                    continue
    except OSError:
        pass
    return last


def write(d, state, op):
    sdir, cur, bak, hist = paths(d)
    os.makedirs(sdir, exist_ok=True)
    state["updated"] = now()
    data = json.dumps(state, indent=1, sort_keys=True)
    if len(data.encode()) > MAX_BYTES:
        sys.exit(json.dumps({"ok": False, "error": f"state would be {len(data)} bytes, limit {MAX_BYTES}. Store big data in a file and record its path with `result`."}))
    with open(hist, "a") as f:
        f.write(json.dumps({"t": state["updated"], "op": op, "state": state}, sort_keys=True) + "\n")
        f.flush(); os.fsync(f.fileno())
    if os.path.getsize(hist) > 256 * 1024:  # keep the log small: last 200 changes
        with open(hist) as f:
            keep = list(deque(f, 200))
        with open(hist + ".tmp", "w") as f:
            f.writelines(keep)
        os.replace(hist + ".tmp", hist)
    tmp = cur + ".tmp"
    with open(tmp, "w") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    if os.path.exists(cur):
        try:
            with open(cur) as f:
                json.load(f)
            os.replace(cur, bak)
        except ValueError:
            pass
    os.replace(tmp, cur)


def need(d):
    s = load(d)
    if s is None:
        sys.exit(json.dumps({"ok": False, "error": "no readable state. Run `recover` or `init`."}))
    return s


def parse_val(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def tail(path, n=3):
    try:
        with open(path) as f:
            return [json.loads(l) for l in deque(f, n)]
    except (OSError, ValueError):
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "show", "set", "done", "result", "check", "recover"])
    ap.add_argument("dir")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--shot")
    ap.add_argument("--mode", default="filmmaker")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    d = a.dir

    if a.cmd == "init":
        if load(d) is not None:
            sys.exit(json.dumps({"ok": False, "error": "state already exists; use show or set"}))
        st = {"shot": a.shot or os.path.basename(os.path.abspath(d)), "mode": a.mode,
              "learning": False, "budget": "balanced", "free_only": True,
              "stage": STAGES[0], "done": [], "facts": {}, "results": {}, "open": []}
        write(d, st, "init")
        print(json.dumps({"ok": True, "stage": st["stage"]}))

    elif a.cmd == "show":
        warn = []
        st = load(d, warn)
        if st is None:
            sys.exit(json.dumps({"ok": False, "error": "no readable state. Run `recover` or `init`."}))
        lines = warn + [f"shot {st['shot']} | mode {st['mode']} | learning {'on' if st['learning'] else 'off'} | budget {st['budget']} | free only {'on' if st['free_only'] else 'off'}",
                 f"stage {st['stage']} | done: {', '.join(st['done']) or 'none'}"]
        if st["facts"]:
            lines.append("facts: " + "; ".join(f"{k}={v}" for k, v in st["facts"].items()))
        if st["results"]:
            lines.append("results: " + "; ".join(f"{k}={v['path']}" for k, v in st["results"].items()))
        if st["open"]:
            lines.append("open: " + "; ".join(st["open"]))
        for e in tail(paths(d)[3]):
            lines.append(f"  {e['t']} {e['op']}")
        print("\n".join(lines))

    elif a.cmd == "set":
        st = need(d)
        for kv in a.args:
            k, _, v = kv.partition("=")
            node, parts = st, k.split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = parse_val(v)
        write(d, st, "set " + " ".join(a.args))
        print(json.dumps({"ok": True}))

    elif a.cmd == "done":
        st = need(d)
        stage = a.args[0]
        if stage not in st["done"]:
            st["done"].append(stage)
        rest = [s for s in STAGES if s not in st["done"]]
        st["stage"] = rest[0] if rest else "finished"
        if a.note:
            st.setdefault("facts", {})[f"{stage}_note"] = a.note[:160]
        write(d, st, f"done {stage}")
        print(json.dumps({"ok": True, "next": st["stage"]}))

    elif a.cmd == "result":
        st = need(d)
        name, p = a.args[0], a.args[1]
        if not os.path.exists(p):
            sys.exit(json.dumps({"ok": False, "error": f"{p} does not exist"}))
        s = os.stat(p)
        st["results"][name] = {"path": p, "size": s.st_size, "mtime": int(s.st_mtime)}
        write(d, st, f"result {name}")
        print(json.dumps({"ok": True}))

    elif a.cmd == "check":
        st = need(d)
        r = st["results"].get(a.args[0])
        if not r:
            print(json.dumps({"valid": False, "reason": "not recorded"})); return
        if not os.path.exists(r["path"]):
            print(json.dumps({"valid": False, "reason": "file missing"})); return
        s = os.stat(r["path"])
        ok = s.st_size == r["size"] and int(s.st_mtime) == r["mtime"]
        print(json.dumps({"valid": ok, "path": r["path"], "reason": "unchanged" if ok else "file changed since recorded"}))

    elif a.cmd == "recover":
        _, cur, bak, hist = paths(d)
        try:
            with open(cur) as f:
                json.load(f)
            print(json.dumps({"ok": True, "source": "state.json was fine"})); return
        except (OSError, ValueError):
            pass
        src, st = None, None
        last = last_history(hist)  # newest: history is written before state.json
        if last:
            st, src = last["state"], "history"
        else:
            try:
                with open(bak) as f:
                    st, src = json.load(f), "backup"
            except (OSError, ValueError):
                pass
        if st is None:
            sys.exit(json.dumps({"ok": False, "error": "nothing to recover from"}))
        write(d, st, f"recover from {src}")
        print(json.dumps({"ok": True, "source": src, "stage": st["stage"]}))


if __name__ == "__main__":
    main()
