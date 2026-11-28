"""Per-shot event log: what the engine actually did, compact and append-only.

Lives in <shot_dir>/state/:
  events.<machine>.jsonl    one file per machine (mac, cowork-vm, ...): one JSON object per
                            line with a CRC of its own content. Machines never append to the
                            same file, so the Mac and the Cowork VM cannot interleave writes;
                            processes on one machine coordinate with an OS lock.
  events.<machine>.1.jsonl  previous generation after rotation
  events.jsonl              legacy single log (2.1.0), still read
  snapshots/<sha>.txt       deduplicated copies of scripts that ran (small text only, never
                            stored when they look like they contain a secret)

Kinds:
  op.start / op.end   an engine command; linked by "op_id"
  op.interrupted      written by `vfx.py event reconcile` for a start whose process died
  note                plain narration from an agent or the user ("source" says who)
  snapshot            a script was recorded before it ran (path, sha, +/- lines vs last)

Reading never trusts a line blindly: bad CRC, torn or oversized lines are counted
and skipped. Status of an op is derived, never assumed: a start without an end is
"running" only while its process is alive on this machine; dead means
"interrupted"; another machine's op is "unknown" until its deadline passes.
"""
import difflib
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
import zlib

from .common import FileLock

MAX_LINE = 4096
ROTATE_BYTES = 2 * 1024 * 1024
SNAP_MAX = 256 * 1024
SNAP_STORE_MAX = 32 * 1024 * 1024
STATUSES = ("PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE")


def paths(shot, machine=None):
    s = os.path.join(shot, "state")
    m = machine or machine_kind()
    return {"dir": s, "log": os.path.join(s, f"events.{m}.jsonl"), "old": os.path.join(s, f"events.{m}.1.jsonl"),
            "lock": os.path.join(s, f".events.{m}.lock"), "snaps": os.path.join(s, "snapshots"),
            "legacy": os.path.join(s, "events.jsonl")}


LOG_RE = re.compile(r"^events(\.[a-z0-9-]{1,32})?(\.1)?\.jsonl$")


def log_files(shot, include_old=True):
    """Every event log in the shot (all machines), oldest generation first."""
    d = os.path.join(shot, "state")
    try:
        names = [n for n in os.listdir(d) if LOG_RE.match(n) and not os.path.islink(os.path.join(d, n))]
    except OSError:
        return []
    if not include_old:
        names = [n for n in names if not n.endswith(".1.jsonl")]
    return [os.path.join(d, n) for n in sorted(names, key=lambda n: (not n.endswith(".1.jsonl"), n))]


SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("API key", re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*")),
    ("password or key assignment", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|passw(or)?d|access[_-]?key|auth)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
]


def find_secret(text):
    """Name of the first secret-looking pattern in text, or None."""
    for name, rx in SECRET_PATTERNS:
        if rx.search(text):
            return name
    return None


def redact(text):
    for _, rx in SECRET_PATTERNS:
        text = rx.sub("[redacted]", text)
    return text


def host_id():
    return f"{socket.gethostname()}|{sys.platform}"


def machine_kind(platform=None, home=None, hostname=None):
    """'mac' for native macOS, 'cowork-vm' for the Cowork Linux VM, else the platform."""
    platform = platform or sys.platform
    home = home if home is not None else os.path.expanduser("~")
    hostname = hostname if hostname is not None else socket.gethostname()
    if platform == "darwin":
        return "mac"
    if platform.startswith("linux") and (home.startswith("/sessions/") or hostname == "claude"):
        return "cowork-vm"
    return "windows" if platform == "win32" else platform


def pid_start(pid):
    """Start time of a process (a string), to tell a reused PID from the original."""
    try:
        if sys.platform.startswith("linux"):
            with open(f"/proc/{int(pid)}/stat") as f:
                return f.read().rsplit(")", 1)[1].split()[19]
        if sys.platform == "darwin":
            r = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() or None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None
    return None


def rel(shot, path):
    """Shot-relative path for anything inside the shot, so events read the same on
    the Mac and in the Cowork VM (which mounts the SSD at a different path)."""
    if not isinstance(path, str) or not path:
        return path
    ap, root = os.path.abspath(path), os.path.abspath(shot)
    try:
        if os.path.commonpath([ap, root]) == root:
            return os.path.relpath(ap, root)
    except ValueError:
        pass
    return path


def _clip(v, n=300, depth=0):
    if isinstance(v, str):
        v = redact(v) if len(v) < 20000 else v[:20000]
        return v if len(v) <= n else v[:n] + "..."
    if isinstance(v, (list, tuple)):
        items = [_clip(x, n, depth + 1) for x in list(v)[:20]]
        return items + [f"... {len(v) - 20} more"] if len(v) > 20 else items
    if isinstance(v, dict):
        if depth > 2:
            return "{...}"
        return {str(k)[:60]: _clip(x, n, depth + 1) for k, x in list(v.items())[:30]}
    if v is None or isinstance(v, (bool, int, float)):
        return v
    return _clip(str(v), n)


def _line(ev):
    body = json.dumps(ev, sort_keys=True, separators=(",", ":"), default=str)
    return json.dumps({**ev, "crc": zlib.crc32(body.encode())}, sort_keys=True, separators=(",", ":"), default=str)


def append(shot, kind, **fields):
    """Append one event and return it. Fields are clipped so a line stays under MAX_LINE."""
    p = paths(shot)
    os.makedirs(p["dir"], exist_ok=True)
    ev = {"v": 1, "id": uuid.uuid4().hex[:12], "t": round(time.time(), 6), "kind": kind,
          "host": host_id(), "machine": machine_kind(), "pid": os.getpid()}
    ev.update({k: _clip(v) for k, v in fields.items() if v is not None})
    line = _line(ev)
    if len(line) > MAX_LINE:
        for k in ("args", "outputs", "errors", "summary", "inputs", "detail"):
            if k in ev:
                ev[k] = _clip(ev[k], 60)
        ev["clipped"] = True
        line = _line(ev)
        if len(line) > MAX_LINE:
            ev = {k: ev[k] for k in ("v", "id", "t", "kind", "host", "machine", "pid", "op", "op_id", "status") if k in ev}
            ev["clipped"] = True
            line = _line(ev)
    with FileLock(p["lock"], timeout=10):
        try:
            if os.path.getsize(p["log"]) > ROTATE_BYTES:
                os.replace(p["log"], p["old"])
        except OSError:
            pass
        fd = os.open(p["log"], os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
    return ev


def parse_lines(data):
    """Parse complete lines from bytes. Returns (events, bad_count, consumed_bytes).
    An unterminated last line is left unconsumed (it may still be being written)."""
    events, bad, used = [], 0, 0
    while True:
        nl = data.find(b"\n", used)
        if nl < 0:
            break
        raw, used = data[used:nl], nl + 1
        if not raw.strip():
            continue
        if len(raw) > MAX_LINE * 2:
            bad += 1
            continue
        try:
            ev = json.loads(raw)
            crc = ev.pop("crc")
            body = json.dumps(ev, sort_keys=True, separators=(",", ":"), default=str)
            if not isinstance(crc, int) or zlib.crc32(body.encode()) != crc or "kind" not in ev:
                bad += 1
                continue
        except (ValueError, KeyError, AttributeError, TypeError):
            bad += 1
            continue
        events.append(ev)
    return events, bad, used


def read_file(path, offset=0):
    """Events in one log file from offset. Returns (events, new_offset, bad_count)."""
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        return [], offset, 0
    e, b, used = parse_lines(data)
    return e, offset + used, b


def read(shot, include_old=True):
    """All events of the shot from every machine's log, in time order. Returns (events, None, bad_count)."""
    events, bad = [], 0
    for p in log_files(shot, include_old):
        e, _, b = read_file(p)
        events += e
        bad += b
    events.sort(key=lambda e: e.get("t") or 0)  # stable: append order kept within a file
    return events, None, bad


class Op:
    """Context manager: op.start on enter, op.end on exit (also on exceptions and SIGTERM).
    Set .status / .summary / .outputs / .errors before leaving."""

    def __init__(self, shot, op, args=None, timeout=None, title=None, purpose=None, component=None):
        self.shot, self.op, self.args, self.timeout = shot, op, args, timeout
        self.described = {"title": title, "purpose": purpose, "component": component}
        self.op_id, self.t0 = uuid.uuid4().hex[:12], None
        self.status, self.summary, self.outputs, self.errors = "UNKNOWN", None, None, None

    def __enter__(self):
        self.t0 = time.time()
        append(self.shot, "op.start", op=self.op, op_id=self.op_id, args=self.args, timeout=self.timeout,
               pid_start=pid_start(os.getpid()), **self.described)
        return self

    def __exit__(self, et, ev, tb):
        if et is not None and self.status == "UNKNOWN":
            self.status = "FAIL"
            self.errors = (self.errors or []) + [f"{et.__name__}: {ev}"[:300]]
        try:
            append(self.shot, "op.end", op=self.op, op_id=self.op_id, status=self.status,
                   dur=round(time.time() - self.t0, 3), summary=self.summary, outputs=self.outputs, errors=self.errors)
        except Exception:
            pass  # never hide the command's own result because logging failed
        return False


def derive(events, now=None, here=None, alive=None, started=None):
    """Fold events into operations with a derived state:
    PASS/FAIL/UNKNOWN/NOT_APPLICABLE (finished), running, interrupted, unknown-remote."""
    from .common import pid_alive
    now = time.time() if now is None else now
    here = here or host_id()
    alive = alive or pid_alive
    started = started or pid_start
    ops, order = {}, []
    for e in events:
        k = e.get("kind")
        if k == "op.start":
            ops[e.get("op_id")] = {"op_id": e.get("op_id"), "op": e.get("op"), "t": e.get("t"), "host": e.get("host"),
                                   "machine": e.get("machine"), "pid": e.get("pid"), "pid_start": e.get("pid_start"),
                                   "args": e.get("args"), "timeout": e.get("timeout"), "state": None,
                                   "title": e.get("title"), "purpose": e.get("purpose"), "component": e.get("component")}
            order.append(e.get("op_id"))
        elif k in ("op.end", "op.interrupted") and e.get("op_id") in ops:
            o = ops[e["op_id"]]
            o.update({"state": e.get("status", "FAIL") if k == "op.end" else "interrupted", "end": e.get("t"),
                      "dur": e.get("dur"), "summary": e.get("summary"), "outputs": e.get("outputs"),
                      "errors": e.get("errors") if k == "op.end" else [e.get("detail") or "process ended without an end event"]})
    for oid in order:
        o = ops[oid]
        if o["state"] is not None:
            continue
        if o["host"] == here:
            live = alive(o["pid"])
            if live and o.get("pid_start") and started(o["pid"]) not in (None, o["pid_start"]):
                live = False  # PID reused by another process
            o["state"] = "running" if live else "interrupted"
            if not live:
                o["errors"] = ["process ended without an end event"]
        elif o.get("timeout") and now > (o["t"] or 0) + o["timeout"] + 60:
            o["state"] = "interrupted"
            o["errors"] = ["deadline passed with no end event (other machine)"]
        else:
            o["state"] = "unknown-remote"
    return [ops[i] for i in order]


def reconcile(shot):
    """Write op.interrupted for starts on this machine whose process is gone. Returns their ids."""
    evs, _, _ = read(shot)
    gone = [o for o in derive(evs) if o["state"] == "interrupted" and o["host"] == host_id()
            and o.get("end") is None]
    for o in gone:
        append(shot, "op.interrupted", op=o["op"], op_id=o["op_id"], detail="process ended without an end event")
    return [o["op_id"] for o in gone]


def _snap_store_size(d):
    try:
        return sum(e.stat().st_size for e in os.scandir(d) if e.is_file(follow_symlinks=False))
    except OSError:
        return 0


def snapshot(shot, path, label=None):
    """Record a script before it runs. Stores small text files once (by hash) and
    logs +/- line counts against the previous snapshot with the same label."""
    p = paths(shot)
    label = label or os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read(SNAP_MAX + 1)
    size = os.path.getsize(path)
    sha = hashlib.sha256(data if size <= SNAP_MAX else data + str(size).encode()).hexdigest()[:16]
    fields = {"path": rel(shot, path), "label": label, "sha": sha, "size": size}
    text = None
    if size > SNAP_MAX:
        fields["stored"] = False
        fields["detail"] = f"over {SNAP_MAX // 1024} KB, hash only"
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            fields["stored"] = False
            fields["detail"] = "not UTF-8 text, hash only"
        if text is not None and find_secret(text):
            fields["stored"] = False
            fields["detail"] = f"withheld: looks like it contains a secret ({find_secret(text)}); hash only"
            text = None
    if text is not None:
        os.makedirs(p["snaps"], exist_ok=True)
        dest = os.path.join(p["snaps"], sha + ".txt")
        if os.path.exists(dest):
            fields["stored"] = True
        elif _snap_store_size(p["snaps"]) + size > SNAP_STORE_MAX:
            fields["stored"] = False
            fields["detail"] = "snapshot store full, hash only"
        else:
            tmp = dest + f".{os.getpid()}.tmp"
            with open(tmp, "wb") as f:  # exact bytes: no newline translation on Windows
                f.write(data)
            os.replace(tmp, dest)
            fields["stored"] = True
    evs, _, _ = read(shot)
    prev = next((e for e in reversed(evs) if e.get("kind") == "snapshot" and e.get("label") == label), None)
    if prev:
        fields["prev"] = prev.get("sha")
        old = load_snapshot(shot, prev.get("sha")) if prev.get("stored") else None
        if old is not None and text is not None:
            plus = minus = 0
            for ln in difflib.unified_diff(old.splitlines(), text.splitlines(), lineterm="", n=0):
                if ln.startswith("+") and not ln.startswith("+++"):
                    plus += 1
                elif ln.startswith("-") and not ln.startswith("---"):
                    minus += 1
            fields["added"], fields["removed"] = plus, minus
    return append(shot, "snapshot", **fields)


def load_snapshot(shot, sha):
    if not isinstance(sha, str) or len(sha) != 16 or any(c not in "0123456789abcdef" for c in sha):
        return None
    try:
        with open(os.path.join(paths(shot)["snaps"], sha + ".txt"), encoding="utf-8", newline="") as f:
            return f.read(SNAP_MAX + 1)
    except OSError:
        return None


def diff(shot, a, b, context=3, max_lines=400):
    old, new = load_snapshot(shot, a), load_snapshot(shot, b)
    if old is None or new is None:
        return None
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), a, b, lineterm="", n=context))
    return lines[:max_lines] + ([f"... {len(lines) - max_lines} more lines"] if len(lines) > max_lines else [])


SKIP_DIRS = {"state", "__pycache__", ".git", "node_modules"}


def _referenced(events, root):
    """path -> latest event time that mentioned it (outputs, snapshot path, args).
    Relative paths are resolved against the shot folder."""
    seen = {}

    def add(v, t):
        if isinstance(v, str) and v and not v.startswith("-") and len(v) < 1024:
            ap = os.path.abspath(v if os.path.isabs(v) else os.path.join(root, v))
            seen[ap] = max(seen.get(ap, 0), t)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add(x, t)
        elif isinstance(v, dict):
            for x in v.values():
                add(x, t)
    for e in events:
        t = e.get("t") or 0
        for k in ("outputs", "path", "args"):
            add(e.get(k), t)
    return seen


def scan(shot, events, limit=20000, tolerance=2.0):
    """Files changed after the log began that no engine event accounts for.
    A file counts as recorded when an event at or after its mtime names the file
    or a folder containing it. Returns {"since", "files": [...], "scanned", "truncated"}."""
    starts = [e.get("t") for e in events if e.get("t")]
    if not starts:
        return {"since": None, "files": [], "scanned": 0, "truncated": False}
    since = min(starts)
    root = os.path.abspath(shot)
    refs = _referenced(events, root)
    found, scanned, truncated = [], 0, False
    for dirpath, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not (dirpath == root and d in SKIP_DIRS) and d not in ("__pycache__",)]
        for name in files:
            if name.startswith("."):
                continue
            scanned += 1
            if scanned > limit:
                truncated = True
                break
            fp = os.path.join(dirpath, name)
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            if st.st_mtime <= since + tolerance:
                continue
            covered, q = False, fp
            while q.startswith(root) and q != os.path.dirname(q):
                if refs.get(q, 0) >= st.st_mtime - tolerance:
                    covered = True
                    break
                q = os.path.dirname(q)
            if not covered:
                found.append({"path": os.path.relpath(fp, root), "mtime": round(st.st_mtime, 1), "size": st.st_size})
        if truncated:
            break
    found.sort(key=lambda x: -x["mtime"])
    return {"since": since, "files": found[:200], "count": len(found), "scanned": scanned, "truncated": truncated}
