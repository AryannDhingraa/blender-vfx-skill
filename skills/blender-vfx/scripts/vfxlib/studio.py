"""VFX Studio viewer: local, read-only, standard library only.

  vfx.py studio --root /Volumes/SSD/vfx [--port 8765] [--open]
  vfx.py studio --selftest [--idle-seconds 60] [--report FILE]

Safety:
- Binds to 127.0.0.1 only. Requests must carry Host 127.0.0.1:<port> or localhost:<port>.
- A fresh token per launch, printed once. /login?t=TOKEN swaps it for an HttpOnly,
  SameSite=Strict session cookie; every other request needs that cookie.
- GET only. No endpoint writes, runs or uploads anything.
- Files: only images and stored snapshots inside a discovered shot folder. Hidden
  names, symlinks anywhere on the path, '..', absolute paths and names that look
  like secrets are refused. Private config and the token are never served.
- The server reads event logs; it never writes them. Changes on disk that no event
  explains are listed separately as "unrecorded".
"""
import collections
import hmac
import http.client
import http.cookies
import http.server
import json
import os
import queue
import secrets
import socket
import stat
import sys
import threading
import time
import urllib.parse

from . import __version__
from . import events as ev

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(SCRIPTS, "studio_ui")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
DENY_WORDS = ("token", "secret", "credential", "password", "passwd", "private", ".key", ".pem", "id_rsa", "id_ed25519")
PREFLIGHT_NAMES = ("mac", "cowork-vm", "linux", "windows")
MAX_IMAGE = 30 * 1024 * 1024
POLL_S = 0.5
DISCOVER_S = 30.0
MAX_CLIENTS = 8
KEEP_EVENTS = 300
MAX_DEPTH = 4
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}


def safe_path(base, rel, exts=None, max_size=MAX_IMAGE):
    """Resolve rel inside base, refusing anything that could escape or expose secrets.
    Returns the real path or None."""
    if not isinstance(rel, str) or not rel or len(rel) > 1024 or "\x00" in rel or "\\" in rel:
        return None
    if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        return None
    parts = rel.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return None
    low = rel.lower()
    if any(w in low for w in DENY_WORDS):
        return None
    if exts is not None and os.path.splitext(low)[1] not in exts:
        return None
    base_real = os.path.realpath(base)
    cur = base
    for p in parts:
        cur = os.path.join(cur, p)
        if os.path.islink(cur):
            return None
    real = os.path.realpath(cur)
    try:
        if os.path.commonpath([real, base_real]) != base_real:
            return None
        st = os.stat(real)
    except (OSError, ValueError):
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > max_size:
        return None
    return real


class Alerts:
    """Deduplicated alerts from deterministic rules. An alert is raised once per condition,
    keeps a count and last-seen time, and resolves when the condition ends."""
    SEV = {"critical": 0, "warning": 1, "info": 2}
    NOT_MONITORED = ["Approval requests: arrive with the production runner (M2)",
                     "Worker disconnection: no remote workers yet",
                     "Correction budgets: arrive with the quality inspector"]

    def __init__(self, started):
        self.started, self.items, self.since = started, {}, {}
        self.version = 0

    def _raise(self, key, sev, title, detail, now, shot=None):
        a = self.items.get(key)
        if a and a["active"]:
            a["last"] = now
            return
        if a:
            a.update({"active": True, "last": now, "count": a["count"] + 1, "sev": sev, "title": title, "detail": detail})
        else:
            self.items[key] = {"key": key, "sev": sev, "title": title, "detail": detail, "shot": shot,
                               "first": now, "last": now, "count": 1, "active": True}
        self.version += 1

    def update(self, shots, tel, now, root):
        live = set()

        def hit(key, *a, **k):
            live.add(key)
            self._raise(key, *a, **k)
        from .plain import describe
        for sid, ops in shots:
            ok_at = {}
            for o in ops:
                if o["state"] == "PASS":
                    ok_at[o["op"]] = max(ok_at.get(o["op"], 0), o.get("t") or 0)
            for o in ops:
                title = o.get("title") or describe(o["op"])[0]
                key = f"op:{sid}:{o['op_id']}"
                if o["state"] in ("FAIL", "interrupted") and ok_at.get(o["op"], 0) <= (o.get("t") or 0):
                    word = "failed" if o["state"] == "FAIL" else "stopped before finishing"
                    hit(key, "warning", f"{title} {word}", "; ".join(map(str, o.get("errors") or []))[:200], now, sid)
                elif o["state"] == "running" and o.get("timeout") and now > (o.get("t") or now) + o["timeout"]:
                    hit(key + ":stall", "warning", f"{title} looks stalled", "running past its time limit", now, sid)
                elif o["state"] == "PASS" and o["op"] in ("run", "resume") and (o.get("end") or 0) >= self.started \
                        and now - (o.get("end") or 0) < 600:
                    hit(key, "info", f"{title} finished", f"took {o.get('dur')} s", now, sid)
        if tel:
            pr = tel.get("pressure") or {}
            lvl = pr.get("level") if pr.get("available") else None
            if lvl in ("warning", "critical"):
                self.since.setdefault("pressure", now)
                if now - self.since["pressure"] >= 60:
                    hit("memory-pressure", "critical" if lvl == "critical" else "warning", "Memory pressure is high",
                        f"{lvl} for {int(now - self.since['pressure'])} s", now)
            else:
                self.since.pop("pressure", None)
            d = tel.get("disk") or {}
            if d.get("available") and (d["free_pct"] < 10 or d["free_gb"] < 50):
                crit = d["free_pct"] < 5 or d["free_gb"] < 20
                hit("disk-low", "critical" if crit else "warning", "Storage is running low",
                    f"{d['free_gb']} GB free ({d['free_pct']}%) on {os.path.basename(d.get('path') or '') or d.get('path')}", now)
            th = tel.get("thermal") or {}
            if th.get("available") and th.get("state") in ("serious", "critical"):
                hit("thermal", "critical" if th["state"] == "critical" else "warning", "The Mac is running hot",
                    f"thermal state {th['state']}: macOS may slow the CPU and GPU", now)
        for k, a in self.items.items():
            if a["active"] and k not in live:
                a["active"] = False
                a["resolved"] = now
                self.version += 1

    def list(self):
        act = sorted((a for a in self.items.values() if a["active"]), key=lambda a: (self.SEV[a["sev"]], -a["last"]))
        old = sorted((a for a in self.items.values() if not a["active"]), key=lambda a: -a.get("resolved", 0))[:10]
        return {"active": act, "recent": old, "not_monitored": self.NOT_MONITORED, "version": self.version}


class Hub:
    """Discovers shots under root, tails every machine's event log in them and fans new events out."""

    def __init__(self, root, telemetry_s=10.0, discover_s=10.0):
        from .telemetry import Sampler
        self.root = os.path.realpath(root)
        self.shots = {}
        self.lock = threading.Lock()
        self.clients = set()
        self.stop = threading.Event()
        self.started = time.time()
        self.latency = collections.deque(maxlen=200)
        self.cpu = collections.deque(maxlen=120)
        self.scan_cache = {}
        self.here = ev.host_id()
        self.seq = 0
        self.telemetry_s, self.discover_s = telemetry_s, discover_s
        self.sampler = Sampler(self.root)
        self.telemetry = None
        self.alerts = Alerts(self.started)
        self.discover_cost = None

    def discover(self):
        t0 = time.time()
        found = {}
        stack = [(self.root, 0)]
        visited = 0
        while stack and visited < 5000:
            d, depth = stack.pop()
            visited += 1
            st_dir = os.path.join(d, "state")
            if os.path.isdir(st_dir) and not os.path.islink(st_dir) and (
                    os.path.isfile(os.path.join(st_dir, "state.json")) or ev.log_files(d)):
                sid = os.path.relpath(d, self.root).replace(os.sep, "/")
                found[sid] = d
            if depth >= MAX_DEPTH:
                continue
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                if e.name.startswith(".") or e.name in ("state", "__pycache__", "node_modules"):
                    continue
                if d == os.path.join(self.root, "_studio") and e.name == "engine":
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append((e.path, depth + 1))
                except OSError:
                    continue
        with self.lock:
            for sid, path in found.items():
                if sid not in self.shots:
                    self.shots[sid] = {"path": path, "files": {}, "events": collections.deque(maxlen=KEEP_EVENTS),
                                       "bad": 0, "loaded": False, "found": time.time()}
            for sid in list(self.shots):
                if sid not in found:
                    del self.shots[sid]
        self.discover_cost = {"seconds": round(time.time() - t0, 4), "dirs": visited}

    def _load(self, s):
        evs, bad, files = [], 0, {}
        for p in ev.log_files(s["path"]):
            try:
                st = os.stat(p)
            except OSError:
                continue
            e, off, b = ev.read_file(p)
            evs += e
            bad += b
            files[p] = {"off": off, "ino": st.st_ino}
        evs.sort(key=lambda e: e.get("t") or 0)
        s.update({"files": files, "bad": bad, "loaded": True})
        s["events"].clear()
        s["events"].extend(evs)
        return evs

    def poll_once(self):
        now = time.time()
        with self.lock:
            items = list(self.shots.items())
        changed = False
        for sid, s in items:
            if not s["loaded"]:
                evs = self._load(s)
                if s["found"] > self.started + 1:  # appeared while running: push what is new
                    for e in evs:
                        if (e.get("t") or 0) >= self.started:
                            self.latency.append(max(0.0, now - e["t"]))
                            self.broadcast({"type": "event", "shot": sid, "event": e})
                            changed = True
                continue
            current = set(ev.log_files(s["path"]))
            rotated = False
            for p in set(s["files"]) - current:
                rotated = True
            new = []
            for p in sorted(current):
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                f = s["files"].get(p)
                if f is None:
                    f = s["files"][p] = {"off": 0, "ino": st.st_ino}
                if st.st_ino != f["ino"] or st.st_size < f["off"]:
                    rotated = True
                    break
                if st.st_size > f["off"]:
                    e, off, b = ev.read_file(p, f["off"])
                    f["off"] = off
                    s["bad"] += b
                    new += e
            if rotated:
                self._load(s)
                self.broadcast({"type": "reload", "shot": sid})
                changed = True
                continue
            new.sort(key=lambda e: e.get("t") or 0)
            for e in new:
                s["events"].append(e)
                if e.get("t") and e["t"] >= self.started:
                    self.latency.append(max(0.0, now - e["t"]))
                self.broadcast({"type": "event", "shot": sid, "event": e})
                changed = True
        return changed

    def _alerts(self, now):
        with self.lock:
            items = [(sid, list(s["events"])) for sid, s in self.shots.items()]
        v = self.alerts.version
        self.alerts.update([(sid, ev.derive(evs, now=now, here=self.here)) for sid, evs in items], self.telemetry, now, self.root)
        if self.alerts.version != v:
            self.broadcast({"type": "alerts", "alerts": self.alerts.list()})

    def loop(self):
        last_disc, last_cpu, cpu0 = time.time(), time.time(), time.process_time()
        last_tel, last_alert = time.time() - self.telemetry_s + 1.0, 0.0  # first reading 1 s after start
        while not self.stop.is_set():
            t = time.time()
            try:
                if t - last_disc > self.discover_s:
                    self.discover()
                    last_disc = t
                changed = self.poll_once()
                tel_every = self.telemetry_s if self.clients else max(60.0, self.telemetry_s)
                if self.telemetry_s > 0 and t - last_tel >= tel_every:
                    self.telemetry = self.sampler.sample()
                    last_tel = t
                    self.broadcast({"type": "telemetry", "telemetry": self.telemetry})
                    changed = True
                if changed or t - last_alert > 5:
                    self._alerts(t)
                    last_alert = t
            except Exception as e:  # keep serving; surface the problem
                self.broadcast({"type": "error", "error": str(e)[:200]})
            if t - last_cpu >= 1.0:
                c = time.process_time()
                self.cpu.append((t, (c - cpu0) / max(1e-6, t - last_cpu) * 100.0))
                cpu0, last_cpu = c, t
            self.stop.wait(POLL_S)

    def add_client(self):
        with self.lock:
            if len(self.clients) >= MAX_CLIENTS:
                return None
            q = queue.Queue(maxsize=500)
            self.clients.add(q)
            return q

    def remove_client(self, q):
        with self.lock:
            self.clients.discard(q)

    def broadcast(self, msg):
        with self.lock:
            self.seq += 1
            msg["seq"] = self.seq
            clients = list(self.clients)
        for q in clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass  # that client will see a seq gap and reload

    def metrics(self):
        now = time.time()
        recent = [c for t, c in self.cpu if now - t <= 60]
        lat = sorted(self.latency)
        cost = [c for t, c, _ in self.sampler.cost[1:] if now - t <= 600]  # steady state: first reading loads libraries
        warm = self.sampler.cost[0][1] if self.sampler.cost else None

        def pct(p):
            return round(lat[min(len(lat) - 1, int(p * len(lat)))], 3) if lat else None
        return {"cpu_pct_60s": round(sum(recent) / len(recent), 3) if recent else None, "uptime_s": round(now - self.started),
                "poll_s": POLL_S, "latency_p50_s": pct(0.5), "latency_p95_s": pct(0.95),
                "latency_max_s": round(lat[-1], 3) if lat else None, "clients": len(self.clients),
                "telemetry_every_s": self.telemetry_s, "telemetry_cpu_s_per_sample": round(sum(cost) / len(cost), 4) if cost else None,
                "telemetry_first_sample_cpu_s": round(warm, 4) if warm is not None else None,
                "discover_every_s": self.discover_s, "discover_cost": self.discover_cost, "seq": self.seq}

    def shot_dir(self, sid):
        with self.lock:
            s = self.shots.get(sid)
            return s["path"] if s else None

    def _overview(self, sid, path, ops):
        from . import state as stmod
        st, src, _ = stmod.load(path)
        blends = []
        bd = os.path.join(path, "05_blend")
        if os.path.isdir(bd) and not os.path.islink(bd):
            blends = sorted((e for e in os.scandir(bd) if e.name.endswith(".blend") and e.is_file(follow_symlinks=False)),
                            key=lambda e: -e.stat().st_mtime)
        running = [o for o in ops if o["state"] in ("running", "unknown-remote")]
        imgs = self.images(sid) or []
        return {"stage": st.get("stage") if st else None, "done": st.get("done") if st else [], "mode": st.get("mode") if st else None,
                "version": (st or {}).get("facts", {}).get("version") or (blends[0].name if blends else None),
                "running": running[-3:], "latest_image": imgs[0] if imgs else None, "state_source": src}

    def state(self):
        from .plain import glossary
        from .preflight import load_settings
        out = []
        with self.lock:
            items = [(sid, s["path"], list(s["events"]), s["bad"]) for sid, s in self.shots.items()]
        for sid, path, evs, bad in sorted(items):
            ops = ev.derive(evs, here=self.here)
            counts = collections.Counter(o["state"] for o in ops)
            out.append({"id": sid, "name": os.path.basename(path) if sid != "." else os.path.basename(self.root),
                        "events": evs[-200:], "ops": ops[-150:], "counts": dict(counts), "bad_lines": bad,
                        "last": evs[-1]["t"] if evs else None, "overview": self._overview(sid, path, ops)})
        pre = {}
        for n in PREFLIGHT_NAMES:
            p = os.path.join(self.root, "_studio", "preflight", n + ".json")
            if os.path.isfile(p) and not os.path.islink(p):
                try:
                    with open(p) as f:
                        pre[n] = json.load(f)
                except (OSError, ValueError):
                    pre[n] = {"error": "unreadable report"}
        settings, _, err = load_settings(self.root)
        return {"version": __version__, "root": self.root, "here": self.here, "machine": ev.machine_kind(),
                "shots": out, "preflight": pre, "metrics": self.metrics(), "settings": settings, "settings_error": err,
                "telemetry": self.telemetry, "alerts": self.alerts.list(), "glossary": glossary(), "seq": self.seq}

    def scan(self, sid):
        path = self.shot_dir(sid)
        if not path:
            return None
        c = self.scan_cache.get(sid)
        if c and time.time() - c[0] < 10:
            return c[1]
        with self.lock:
            evs = list(self.shots[sid]["events"])
        res = ev.scan(path, evs)
        self.scan_cache[sid] = (time.time(), res)
        return res

    def images(self, sid):
        path = self.shot_dir(sid)
        if not path:
            return None
        found = {}
        rv = os.path.join(path, "_review")
        if os.path.isdir(rv) and not os.path.islink(rv):
            for dp, dirs, files in os.walk(rv, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                if dp.count(os.sep) - rv.count(os.sep) > 2:
                    dirs[:] = []
                for n in files:
                    rel = os.path.relpath(os.path.join(dp, n), path).replace(os.sep, "/")
                    if safe_path(path, rel, IMAGE_TYPES):
                        found[rel] = os.path.getmtime(os.path.join(dp, n))
        with self.lock:
            evs = list(self.shots[sid]["events"]) if sid in self.shots else []
        for e in evs:
            for o in e.get("outputs") or []:
                if isinstance(o, str) and not os.path.isabs(o) and safe_path(path, o, IMAGE_TYPES):
                    found[o] = os.path.getmtime(os.path.join(path, o))
        return [{"path": k, "mtime": round(v, 1)} for k, v in sorted(found.items(), key=lambda x: -x[1])[:24]]


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, hub, port=8765, token=None, quiet=False):
        super().__init__(("127.0.0.1", port), Handler)
        self.hub = hub
        self.token = token or secrets.token_urlsafe(24)
        self.session = secrets.token_urlsafe(24)
        self.quiet = quiet
        p = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{p}", f"localhost:{p}"}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "vfx-studio"
    sys_version = ""

    def log_message(self, fmt, *args):
        if not self.server.quiet:
            path = urllib.parse.urlsplit(self.path).path  # never log the query (login token)
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} {self.command} {path} {args[1] if len(args) > 1 else ''}\n")

    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        headers = headers or {}
        for k, v in SECURITY_HEADERS.items():
            if k not in headers:
                self.send_header(k, v)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, separators=(",", ":"), default=str), "application/json")

    def _authed(self):
        c = http.cookies.SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return False
        m = c.get("vfxs")
        return bool(m) and hmac.compare_digest(m.value, self.server.session)

    def _refuse(self, *a):
        self._send(405, "read-only viewer", headers={"Allow": "GET"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _refuse

    def do_GET(self):
        if self.headers.get("Host", "") not in self.server.allowed_hosts:
            return self._send(403, "bad host")
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, max_num_fields=8).items()}  # unknown keys ignored
        if u.path == "/login":
            if hmac.compare_digest(q.get("t", ""), self.server.token):
                return self._send(303, "", headers={"Location": "/", "Set-Cookie":
                                  f"vfxs={self.server.session}; HttpOnly; SameSite=Strict; Path=/"})
            return self._send(401, "wrong or expired link: use the one printed in Terminal")
        if not self._authed():
            return self._send(401, "not signed in: open the link printed in Terminal when the viewer started")
        hub = self.server.hub
        if u.path in STATIC:
            name, ctype = STATIC[u.path]
            with open(os.path.join(UI, name), "rb") as f:
                return self._send(200, f.read(), ctype)
        if u.path == "/api/state":
            return self._json(hub.state())
        if u.path == "/api/health":
            return self._json(hub.metrics())
        if u.path == "/api/telemetry":
            return self._json({"telemetry": hub.telemetry, "metrics": hub.metrics()})
        if u.path == "/api/stream":
            return self._stream()
        sid = q.get("shot", "")
        base = hub.shot_dir(sid)
        if u.path in ("/api/scan", "/api/images", "/api/image", "/api/snapshot", "/api/diff") and not base:
            return self._send(404, "unknown shot")
        if u.path == "/api/scan":
            return self._json(hub.scan(sid))
        if u.path == "/api/images":
            return self._json(hub.images(sid))
        if u.path == "/api/image":
            real = safe_path(base, q.get("path", ""), IMAGE_TYPES)
            if not real:
                return self._send(404, "not available")
            with open(real, "rb") as f:
                return self._send(200, f.read(), IMAGE_TYPES[os.path.splitext(real)[1].lower()],
                                  headers={"Cache-Control": "private, max-age=300"})  # URLs carry the file's mtime
        if u.path == "/api/snapshot":
            text = ev.load_snapshot(base, q.get("sha", ""))
            return self._json({"text": text}) if text is not None else self._send(404, "not available")
        if u.path == "/api/diff":
            lines = ev.diff(base, q.get("a", ""), q.get("b", ""))
            return self._json({"lines": lines}) if lines is not None else self._send(404, "not available")
        return self._send(404, "not found")

    def _stream(self):
        hub = self.server.hub
        qd = hub.add_client()
        if qd is None:
            return self._send(503, "too many viewers open")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while not hub.stop.is_set():
                try:
                    msg = qd.get(timeout=15)
                    data = json.dumps(msg, separators=(",", ":"), default=str)
                    self.wfile.write(f"event: {msg['type']}\ndata: {data}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            hub.remove_client(qd)


def start(root, port=8765, quiet=False, token=None, telemetry_s=10.0, discover_s=10.0):
    hub = Hub(root, telemetry_s, discover_s)
    hub.discover()
    hub.poll_once()
    srv = Server(hub, port, token, quiet)
    threading.Thread(target=hub.loop, daemon=True).start()
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()
    return srv


def serve(root, port=8765, open_browser=False, telemetry_s=10.0):
    if not os.path.isdir(root):
        print(json.dumps({"ok": False, "error": f"root not found: {root}"}))
        return 2
    try:
        srv = start(root, port, telemetry_s=telemetry_s)
    except OSError as e:
        print(json.dumps({"ok": False, "error": f"cannot listen on 127.0.0.1:{port}: {e}"}))
        return 2
    url = f"http://127.0.0.1:{srv.server_address[1]}/login?t={srv.token}"
    shots = [s["id"] for s in srv.hub.state()["shots"]]
    print(f"VFX Studio viewer {__version__} (read-only) watching {srv.hub.root}")
    print(f"Shots found: {len(shots)} {shots[:10]}")
    print(f"Open this link in your browser (valid until you stop the viewer):\n  {url}")
    print("Stop with Ctrl+C.", flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    srv.hub.stop.set()
    srv.shutdown()
    return 0


def _req(port, path, cookie=None, host=None, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{port}"}
    if cookie:
        h["Cookie"] = cookie
    c.request(method, path, headers=h)
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, dict(r.getheaders()), body


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def selftest(idle_seconds=60, n_events=20, report=None):
    """Measure the real server on this machine: security checks, idle CPU, update latency
    and interrupted-op handling. Uses a temporary shot; touches nothing else."""
    import subprocess
    import tempfile
    from . import state as st
    from .preflight import write_report
    res = {}

    def check(name, ok, value=None):
        res[name] = {"status": "PASS" if ok else "FAIL", "value": value}
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "root")
        shot = os.path.join(root, "shot010")
        st.init(shot, "shot010")
        os.makedirs(os.path.join(shot, "_review"))
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x00\x00\x00\x00:~\x9bU"
               b"\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82")
        with open(os.path.join(shot, "_review", "sheet.png"), "wb") as f:
            f.write(png)
        outside = os.path.join(tmp, "outside.png")
        with open(outside, "wb") as f:
            f.write(png)
        with open(os.path.join(shot, "notes.txt"), "w") as f:
            f.write("private")
        with open(os.path.join(shot, "_review", "api_token.png"), "wb") as f:
            f.write(png)
        os.makedirs(os.path.join(root, "_studio"))
        with open(os.path.join(root, "_studio", "config.json"), "w") as f:
            f.write('{"learning":"off"}')
        try:
            os.symlink(outside, os.path.join(shot, "_review", "link.png"))
            os.symlink(tmp, os.path.join(shot, "_review", "linkdir"))
            links = True
        except (OSError, NotImplementedError):
            links = False
        srv = start(root, 0, quiet=True, telemetry_s=10.0, discover_s=5.0)
        port = srv.server_address[1]
        try:
            check("binds_loopback_only", srv.server_address[0] == "127.0.0.1", srv.server_address[0])
            ip = _lan_ip()
            if ip and not ip.startswith("127."):
                s = socket.socket()
                s.settimeout(2)
                refused = s.connect_ex((ip, port)) != 0
                s.close()
                check("unreachable_from_lan_address", refused, ip)
            check("no_cookie_refused", _req(port, "/api/state")[0] == 401)
            check("wrong_token_refused", _req(port, "/login?t=wrong")[0] == 401)
            code, hdr, _ = _req(port, f"/login?t={srv.token}")
            cookie = (hdr.get("Set-Cookie") or "").split(";")[0]
            check("login_sets_httponly_cookie", code == 303 and "HttpOnly" in (hdr.get("Set-Cookie") or "")
                  and srv.token not in (hdr.get("Set-Cookie") or ""))
            check("bad_host_refused", _req(port, "/api/state", cookie, host="evil.example:80")[0] == 403)
            check("post_refused", _req(port, "/api/state", cookie, method="POST")[0] == 405)
            code, _, body = _req(port, "/api/state", cookie)
            check("state_ok", code == 200 and b"shot010" in body)
            check("token_not_in_state", srv.token.encode() not in body)
            sid = "shot010"
            q = lambda p: urllib.parse.quote(p)  # noqa: E731
            check("image_served", _req(port, f"/api/image?shot={sid}&path={q('_review/sheet.png')}", cookie)[0] == 200)
            bad = {"traversal": "../outside.png", "absolute": outside, "non_image": "notes.txt", "config": "../_studio/config.json",
                   "secret_name": "_review/api_token.png", "encoded_dots": "_review/%2e%2e/notes.txt", "backslash": "_review\\sheet.png"}
            if links:
                bad.update({"symlink_file": "_review/link.png", "symlink_dir": "_review/linkdir/outside.png"})
            for name, p in bad.items():
                check(f"refuses_{name}", _req(port, f"/api/image?shot={sid}&path={q(p)}", cookie)[0] == 404)
            check("unknown_shot_refused", _req(port, "/api/image?shot=..&path=x.png", cookie)[0] == 404)

            got, seqs, lock = {}, [], threading.Lock()

            def reader():
                s = socket.create_connection(("127.0.0.1", port), timeout=idle_seconds + 30)
                s.sendall(f"GET /api/stream HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nCookie: {cookie}\r\n\r\n".encode())
                buf = b""
                try:
                    while True:
                        chunk = s.recv(65536)
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n\n" in buf:
                            block, buf = buf.split(b"\n\n", 1)
                            for line in block.split(b"\n"):
                                if line.startswith(b"data: "):
                                    m = json.loads(line[6:])
                                    with lock:
                                        seqs.append(m.get("seq"))
                                    e = m.get("event") or {}
                                    if e.get("summary", "").startswith("selftest-"):
                                        with lock:
                                            got[e["summary"]] = time.time()
                except OSError:
                    pass
            threading.Thread(target=reader, daemon=True).start()
            time.sleep(1.5)
            from .telemetry import Sampler
            own = Sampler()._own_cpu  # this process plus the commands it ran (telemetry samples)
            w0, c0 = time.time(), own()
            time.sleep(idle_seconds)
            idle = (own() - c0) / (time.time() - w0) * 100.0
            check("idle_cpu_under_1pct", idle < 1.0, round(idle, 3))
            tel = srv.hub.telemetry or {}
            need = {"darwin": ["cpu", "memory", "disk", "pressure", "swap", "thermal"], "win32": ["cpu", "memory", "disk"]}.get(
                sys.platform, ["cpu", "memory", "disk"] if sys.platform.startswith("linux") else ["disk"])
            check("telemetry_readings", all((tel.get(k) or {}).get("available") for k in need),
                  {k: ({kk: vv for kk, vv in (tel.get(k) or {}).items() if kk != "method"}) for k in
                   ("cpu", "gpu", "memory", "pressure", "swap", "disk", "thermal")})
            m = srv.hub.metrics()
            per = m.get("telemetry_cpu_s_per_sample")
            check("telemetry_overhead_under_0.5pct", per is not None and per / srv.hub.telemetry_s * 100 < 0.5,
                  None if per is None else f"{round(per / srv.hub.telemetry_s * 100, 3)}% ({per} s CPU per sample every {srv.hub.telemetry_s:g} s)")
            t_new = time.time()
            st.init(os.path.join(root, "shot020"), "shot020")
            while time.time() - t_new < srv.hub.discover_s + 5 and "shot020" not in srv.hub.shots:
                time.sleep(0.2)
            took = time.time() - t_new
            check("new_shot_found_quickly", "shot020" in srv.hub.shots and took <= srv.hub.discover_s + 1.5, round(took, 2))
            sent = {}
            for i in range(n_events):
                tag = f"selftest-{i}"
                sent[tag] = time.time()
                ev.append(shot, "note", source="selftest", summary=tag)
                time.sleep(0.4)
            deadline = time.time() + 5
            while time.time() < deadline and len(got) < n_events:
                time.sleep(0.1)
            lat = sorted(got[k] - sent[k] for k in got)
            check("all_events_delivered", len(got) == n_events, f"{len(got)}/{n_events}")
            with lock:
                sq = [x for x in seqs if x is not None]
            check("stream_seq_increasing", bool(sq) and all(b > a for a, b in zip(sq, sq[1:])), f"{len(sq)} messages")
            _, _, body = _req(port, "/api/state", cookie)
            stj = json.loads(body)
            have = {e.get("summary") for sh in stj["shots"] for e in sh["events"]}
            check("state_has_every_event_for_catch_up", all(f"selftest-{i}" in have for i in range(n_events))
                  and stj["seq"] >= (sq[-1] if sq else 0))
            check("update_under_2s", bool(lat) and lat[-1] <= 2.0,
                  {"p50": round(lat[len(lat) // 2], 3) if lat else None, "max": round(lat[-1], 3) if lat else None})
            code = ("import sys,os; sys.path.insert(0, %r)\nfrom vfxlib import events as ev\n"
                    "o = ev.Op(%r, 'selftest-kill').__enter__()\nos._exit(9)\n") % (SCRIPTS, shot)
            subprocess.run([sys.executable, "-c", code], timeout=60)
            time.sleep(POLL_S * 3)
            _, _, body = _req(port, "/api/state", cookie)
            ops = next(s for s in json.loads(body)["shots"] if s["id"] == sid)["ops"]
            k = [o for o in ops if o["op"] == "selftest-kill"]
            check("killed_op_shown_interrupted", bool(k) and k[-1]["state"] == "interrupted", k[-1]["state"] if k else None)
            with open(ev.paths(shot)["log"], "ab") as f:
                f.write(b'{"kind":"note","summary":"forged","crc":1}\n')
            time.sleep(POLL_S * 3)
            _, _, body = _req(port, "/api/state", cookie)
            s = next(s for s in json.loads(body)["shots"] if s["id"] == sid)
            check("forged_line_rejected", s["bad_lines"] >= 1 and not any(e.get("summary") == "forged" for e in s["events"]))
            res["server_metrics"] = {"status": "PASS", "value": srv.hub.metrics()}
        finally:
            srv.hub.stop.set()
            srv.shutdown()
    rep = {"ok": all(v["status"] == "PASS" for v in res.values()), "machine": ev.machine_kind(),
           "python": sys.version.split()[0], "engine": __version__, "time": round(time.time(), 1),
           "idle_seconds": idle_seconds, "results": res}
    if report:
        write_report(rep, path=report)
    return rep
