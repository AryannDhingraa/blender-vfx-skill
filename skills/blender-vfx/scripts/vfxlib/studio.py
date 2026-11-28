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


class Hub:
    """Discovers shots under root, tails their event logs and fans new events out."""

    def __init__(self, root):
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

    def discover(self):
        found = {}
        stack = [(self.root, 0)]
        visited = 0
        while stack and visited < 5000:
            d, depth = stack.pop()
            visited += 1
            st_dir = os.path.join(d, "state")
            if os.path.isfile(os.path.join(st_dir, "state.json")) or os.path.isfile(os.path.join(st_dir, "events.jsonl")):
                if not os.path.islink(st_dir):
                    sid = os.path.relpath(d, self.root).replace(os.sep, "/")
                    found["." if sid == "." else sid] = d
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
                    self.shots[sid] = {"path": path, "offset": 0, "ino": None, "events": collections.deque(maxlen=KEEP_EVENTS),
                                       "bad": 0, "loaded": False}
            for sid in list(self.shots):
                if sid not in found:
                    del self.shots[sid]

    def poll_once(self):
        now = time.time()
        with self.lock:
            items = list(self.shots.items())
        for sid, s in items:
            log = ev.paths(s["path"])["log"]
            try:
                st = os.stat(log)
            except OSError:
                continue
            reset = s["ino"] is not None and (st.st_ino != s["ino"] or st.st_size < s["offset"])
            if reset or not s["loaded"]:
                evs, off, bad = ev.read(s["path"], 0, include_old=True)
                s.update({"offset": off, "ino": st.st_ino, "bad": bad, "loaded": True})
                s["events"].clear()
                s["events"].extend(evs)
                if reset:
                    self.broadcast({"type": "reload", "shot": sid})
                else:  # a log that appeared after start: push what is new since start
                    for e in evs:
                        if e.get("t") and e["t"] >= self.started:
                            self.latency.append(max(0.0, now - e["t"]))
                            self.broadcast({"type": "event", "shot": sid, "event": e})
                continue
            if st.st_size > s["offset"]:
                evs, off, bad = ev.read(s["path"], s["offset"])
                s["offset"], s["bad"] = off, s["bad"] + bad
                for e in evs:
                    s["events"].append(e)
                    if e.get("t") and e["t"] >= self.started:
                        self.latency.append(max(0.0, now - e["t"]))
                    self.broadcast({"type": "event", "shot": sid, "event": e})

    def loop(self):
        last_disc, last_cpu, cpu0 = 0.0, time.time(), time.process_time()
        while not self.stop.is_set():
            t = time.time()
            if t - last_disc > DISCOVER_S:
                self.discover()
                last_disc = t
            try:
                self.poll_once()
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
            clients = list(self.clients)
        for q in clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    def metrics(self):
        now = time.time()
        recent = [c for t, c in self.cpu if now - t <= 60]
        lat = sorted(self.latency)

        def pct(p):
            return round(lat[min(len(lat) - 1, int(p * len(lat)))], 3) if lat else None
        return {"cpu_pct_60s": round(sum(recent) / len(recent), 3) if recent else None, "uptime_s": round(now - self.started),
                "poll_s": POLL_S, "latency_p50_s": pct(0.5), "latency_p95_s": pct(0.95),
                "latency_max_s": round(lat[-1], 3) if lat else None, "clients": len(self.clients)}

    def shot_dir(self, sid):
        with self.lock:
            s = self.shots.get(sid)
            return s["path"] if s else None

    def state(self):
        out = []
        with self.lock:
            items = [(sid, s["path"], list(s["events"]), s["bad"]) for sid, s in self.shots.items()]
        for sid, path, evs, bad in sorted(items):
            ops = ev.derive(evs, here=self.here)
            counts = collections.Counter(o["state"] for o in ops)
            out.append({"id": sid, "name": os.path.basename(path) if sid != "." else os.path.basename(self.root),
                        "events": evs[-200:], "ops": ops[-150:], "counts": dict(counts), "bad_lines": bad,
                        "last": evs[-1]["t"] if evs else None})
        pre = {}
        for n in PREFLIGHT_NAMES:
            p = os.path.join(self.root, "_studio", "preflight", n + ".json")
            if os.path.isfile(p) and not os.path.islink(p):
                try:
                    with open(p) as f:
                        pre[n] = json.load(f)
                except (OSError, ValueError):
                    pre[n] = {"error": "unreadable report"}
        return {"version": __version__, "root": self.root, "here": self.here, "machine": ev.machine_kind(),
                "shots": out, "preflight": pre, "metrics": self.metrics()}

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
            evs = list(self.shots[sid]["events"])
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
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        for k, v in (headers or {}).items():
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
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, max_num_fields=8).items()}
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
                return self._send(200, f.read(), IMAGE_TYPES[os.path.splitext(real)[1].lower()])
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


def start(root, port=8765, quiet=False, token=None):
    hub = Hub(root)
    hub.discover()
    hub.poll_once()
    srv = Server(hub, port, token, quiet)
    threading.Thread(target=hub.loop, daemon=True).start()
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()
    return srv


def serve(root, port=8765, open_browser=False):
    if not os.path.isdir(root):
        print(json.dumps({"ok": False, "error": f"root not found: {root}"}))
        return 2
    try:
        srv = start(root, port)
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
        srv = start(root, 0, quiet=True)
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

            got, lock = {}, threading.Lock()

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
                                    e = m.get("event") or {}
                                    if e.get("summary", "").startswith("selftest-"):
                                        with lock:
                                            got[e["summary"]] = time.time()
                except OSError:
                    pass
            threading.Thread(target=reader, daemon=True).start()
            time.sleep(1.5)
            w0, c0 = time.time(), time.process_time()
            time.sleep(idle_seconds)
            idle = (time.process_time() - c0) / (time.time() - w0) * 100.0
            check("idle_cpu_under_1pct", idle < 1.0, round(idle, 3))
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
            m = srv.hub.metrics()
            res["server_metrics"] = {"status": "PASS", "value": m}
        finally:
            srv.hub.stop.set()
            srv.shutdown()
    rep = {"ok": all(v["status"] == "PASS" for v in res.values()), "machine": ev.machine_kind(),
           "python": sys.version.split()[0], "engine": __version__, "time": round(time.time(), 1),
           "idle_seconds": idle_seconds, "results": res}
    if report:
        write_report(rep, path=report)
    return rep
