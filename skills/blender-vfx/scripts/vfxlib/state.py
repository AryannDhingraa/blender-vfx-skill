"""Per-shot state: small, validated, locked, recoverable.

Lives in <shot_dir>/state/:
  state.json      current state, under MAX_BYTES (paths and fingerprints, never data)
  state.json.bak  previous valid copy
  history.jsonl   append-only, checksummed, trimmed to the last HISTORY_KEEP changes
  .lock           OS lock held during every read-modify-write
  jobs/<id>.json  render and bake job manifests (see jobs.py)

Results are recorded outputs (footage analysis, camera solve, renders) with
fingerprints of their files and the results they were built from. A result
is stale when its files changed, a dependency was redone or went stale, or
its settings changed. Stale results are never deleted automatically.
"""
import copy
import json
import os
import time
import zlib

from .common import FileLock, atomic_write, fingerprint

STAGES = ["brief", "plate", "analyse", "track", "build", "light", "preview",
          "render", "comp", "review", "deliver"]
MODES = {"filmmaker", "vfx-artist"}
BUDGETS = {"economy", "balanced", "quality"}
MAX_BYTES = 4096
HISTORY_KEEP = 200
HISTORY_MAX_BYTES = 256 * 1024


class StateError(Exception):
    pass


def paths(d):
    s = os.path.join(d, "state")
    return {"dir": s, "cur": os.path.join(s, "state.json"), "bak": os.path.join(s, "state.json.bak"),
            "hist": os.path.join(s, "history.jsonl"), "lock": os.path.join(s, ".lock"),
            "jobs": os.path.join(s, "jobs")}


def new_state(shot, mode="filmmaker"):
    return {"v": 1, "seq": 0, "shot": shot, "mode": mode, "learning": False, "budget": "balanced",
            "free_only": True, "stage": STAGES[0], "done": [], "facts": {}, "results": {}, "open": [],
            "updated": ""}


def validate(st):
    """Return a list of problems; empty means valid."""
    if not isinstance(st, dict):
        return ["not an object"]
    errs = []
    types = {"v": int, "seq": int, "shot": str, "mode": str, "learning": bool, "budget": str,
             "free_only": bool, "stage": str, "done": list, "facts": dict, "results": dict, "open": list}
    for k, t in types.items():
        if k not in st:
            errs.append(f"missing {k}")
        elif not isinstance(st[k], t) or (t is int and isinstance(st[k], bool)):
            errs.append(f"{k} should be {t.__name__}")
    if errs:
        return errs
    if st["mode"] not in MODES:
        errs.append(f"mode must be one of {sorted(MODES)}")
    if st["budget"] not in BUDGETS:
        errs.append(f"budget must be one of {sorted(BUDGETS)}")
    if st["stage"] not in STAGES + ["finished"]:
        errs.append(f"unknown stage {st['stage']}")
    for s in st["done"]:
        if s not in STAGES:
            errs.append(f"unknown done stage {s}")
    for name, r in st["results"].items():
        if not isinstance(r, dict) or not isinstance(r.get("paths"), dict) or not isinstance(r.get("deps"), dict) \
                or not isinstance(r.get("at"), int):
            errs.append(f"result {name} malformed")
            continue
        for dep in r["deps"]:
            if dep == name:
                errs.append(f"result {name} depends on itself")
    return errs


def _dump(st):
    return json.dumps(st, sort_keys=True, separators=(",", ":"))


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return None
    return st if not validate(st) else None


def _history_best(hist):
    best = None
    try:
        with open(hist, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    st = e["state"]
                    if zlib.crc32(_dump(st).encode()) != e["crc"] or validate(st):
                        continue
                    if best is None or st["seq"] >= best["seq"]:
                        best = st
                except (ValueError, KeyError, TypeError):
                    continue  # torn or corrupt line: skip it
    except OSError:
        pass
    return best


def load(d):
    """(state, source, problems). source is current, history, backup or None.
    Falls back to the newest checksummed history entry, then the backup."""
    p = paths(d)
    st = _read(p["cur"])
    if st is not None:
        return st, "current", []
    problems = ["state.json missing or invalid"] if os.path.exists(p["cur"]) else []
    hist = _history_best(p["hist"])
    bak = _read(p["bak"])
    cands = [(s, n) for s, n in ((hist, "history"), (bak, "backup")) if s is not None]
    if not cands:
        return None, None, problems
    st, src = max(cands, key=lambda c: c[0]["seq"])
    return st, src, problems + [f"recovered from {src}"]


def _relpath(d, path):
    path = os.path.abspath(path)
    try:
        return os.path.relpath(path, os.path.abspath(d))
    except ValueError:  # other drive on Windows
        return path


def _abspath(d, rel):
    return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(d, rel))


def commit(d, mutate, op, create=False):
    """Locked read-modify-write. mutate(state) changes the copy in place and
    may return a value, which commit returns with the new state."""
    p = paths(d)
    os.makedirs(p["dir"], exist_ok=True)
    with FileLock(p["lock"]):
        st, src, _ = load(d)
        if st is None and not create:
            raise StateError("no readable state; run `state init`")
        if st is not None and create:
            raise StateError("state already exists")
        work = copy.deepcopy(st) if st is not None else None
        ret = mutate(work) if not create else None
        if create:
            work = mutate(None)
        work["seq"] = (st["seq"] if st else 0) + 1
        work["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        errs = validate(work)
        if errs:
            raise StateError("refused, state would be invalid: " + "; ".join(errs))
        data = json.dumps(work, indent=1, sort_keys=True)
        if len(data.encode()) > MAX_BYTES:
            raise StateError(f"refused, state would be {len(data.encode())} bytes (limit {MAX_BYTES}); "
                             "keep data in files and record their paths")
        line = json.dumps({"seq": work["seq"], "t": work["updated"], "op": op[:200],
                           "crc": zlib.crc32(_dump(work).encode()), "state": work}, sort_keys=True)
        with open(p["hist"], "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        if os.path.getsize(p["hist"]) > HISTORY_MAX_BYTES:
            with open(p["hist"], encoding="utf-8") as f:
                keep = f.readlines()[-HISTORY_KEEP:]
            atomic_write(p["hist"], "".join(keep))
        if src == "current":
            os.replace(p["cur"], p["bak"])
        elif st is not None:  # after a recovery, the recovered state becomes the backup
            atomic_write(p["bak"], json.dumps(st, indent=1, sort_keys=True))
        atomic_write(p["cur"], data)
        return work, ret


def init(d, shot, mode="filmmaker"):
    return commit(d, lambda _: new_state(shot, mode), "init", create=True)[0]


def set_values(d, pairs):
    def m(st):
        for k, v in pairs:
            if k in ("seq", "v", "results", "updated", "done"):
                raise StateError(f"{k} is managed by the engine")
            node, parts = st, k.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
                if not isinstance(node, dict):
                    raise StateError(f"{k}: {part} is not an object")
            node[parts[-1]] = v
    return commit(d, m, "set " + ",".join(k for k, _ in pairs))[0]


def done(d, stage, note=""):
    if stage not in STAGES:
        raise StateError(f"unknown stage {stage}")

    def m(st):
        if stage not in st["done"]:
            st["done"].append(stage)
        rest = [s for s in STAGES if s not in st["done"]]
        st["stage"] = rest[0] if rest else "finished"
        if note:
            st["facts"][f"{stage}_note"] = note[:160]
    return commit(d, m, f"done {stage}")[0]


def reopen(d, stage):
    """Go back to a stage: it and every later stage are no longer done."""
    if stage not in STAGES:
        raise StateError(f"unknown stage {stage}")
    later = set(STAGES[STAGES.index(stage):])

    def m(st):
        st["done"] = [s for s in st["done"] if s not in later]
        st["stage"] = stage
    return commit(d, m, f"reopen {stage}")[0]


def record(d, name, files, deps=(), params=None):
    """Record a result: its files (or folders) and the results it was built from."""
    fps = {}
    for f in files:
        fp = fingerprint(f)
        if fp is None:
            raise StateError(f"{f} does not exist")
        fps[_relpath(d, f)] = [fp["kind"], fp["size"], fp["hash"]]
    ph = None if params is None else format(zlib.crc32(json.dumps(params, sort_keys=True).encode()), "08x")

    def m(st):
        dep_at = {}
        for dep in deps:
            if dep not in st["results"]:
                raise StateError(f"dependency {dep} is not recorded")
            if dep == name or name in _upstream(st["results"], dep):
                raise StateError(f"{name} -> {dep} would make a cycle")
            dep_at[dep] = st["results"][dep]["at"]
        st["results"][name] = {"paths": fps, "deps": dep_at, "params": ph, "at": st["seq"] + 1}
    return commit(d, m, f"record {name}")[0]


def _upstream(results, name, seen=None):
    seen = set() if seen is None else seen
    for dep in results.get(name, {}).get("deps", {}):
        if dep not in seen:
            seen.add(dep)
            _upstream(results, dep, seen)
    return seen


def dependents(results, name):
    out, frontier = set(), {name}
    while frontier:
        nxt = {n for n, r in results.items() if set(r["deps"]) & frontier and n not in out}
        out |= nxt
        frontier = nxt
    return out


def check(d, st, name, params=None, _memo=None):
    """{'valid': bool, 'reasons': [...]} without writing anything."""
    memo = {} if _memo is None else _memo
    if name in memo:
        return memo[name]
    memo[name] = {"valid": False, "reasons": ["dependency cycle"]}
    r = st["results"].get(name)
    if r is None:
        res = {"valid": False, "reasons": ["not recorded"]}
    else:
        reasons = []
        for rel, (kind, size, h) in r["paths"].items():
            fp = fingerprint(_abspath(d, rel))
            if fp is None:
                reasons.append(f"{rel} missing")
            elif [fp["kind"], fp["size"], fp["hash"]] != [kind, size, h]:
                reasons.append(f"{rel} changed")
        for dep, at in r["deps"].items():
            dr = st["results"].get(dep)
            if dr is None:
                reasons.append(f"input {dep} was removed")
            elif dr["at"] != at:
                reasons.append(f"input {dep} was redone")
            else:
                sub = check(d, st, dep, None, memo)
                if not sub["valid"]:
                    reasons.append(f"input {dep} is stale")
        if params is not None:
            ph = format(zlib.crc32(json.dumps(params, sort_keys=True).encode()), "08x")
            if ph != r.get("params"):
                reasons.append("settings changed")
        res = {"valid": not reasons, "reasons": reasons}
    memo[name] = res
    return res


def stale(d, st):
    memo = {}
    return {n: check(d, st, n, None, memo)["reasons"] for n in st["results"]
            if not check(d, st, n, None, memo)["valid"]}


def invalidate(d, name):
    """Forget a result and everything built from it. Files are not touched."""
    def m(st):
        if name not in st["results"]:
            raise StateError(f"{name} is not recorded")
        gone = {name} | dependents(st["results"], name)
        for n in gone:
            del st["results"][n]
        return sorted(gone)
    return commit(d, m, f"invalidate {name}")


def summary(d):
    st, src, problems = load(d)
    if st is None:
        return None
    lines = [f"WARNING {p}" for p in problems]
    lines.append(f"shot {st['shot']} | mode {st['mode']} | learning {'on' if st['learning'] else 'off'} | "
                 f"budget {st['budget']} | free only {'on' if st['free_only'] else 'off'}")
    lines.append(f"stage {st['stage']} | done: {', '.join(st['done']) or 'none'}")
    if st["facts"]:
        lines.append("facts: " + "; ".join(f"{k}={v}" for k, v in st["facts"].items()))
    bad = stale(d, st)
    if st["results"]:
        lines.append("results: " + ", ".join(
            f"{n}{' (STALE: ' + '; '.join(bad[n][:2]) + ')' if n in bad else ''}" for n in st["results"]))
    if st["open"]:
        lines.append("open: " + "; ".join(map(str, st["open"])))
    return "\n".join(lines)
