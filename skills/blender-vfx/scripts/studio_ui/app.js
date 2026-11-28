// VFX Studio viewer. Read-only: every request is a GET, all data is shown with textContent.
"use strict";
const S = { data: null, shot: null, tab: "activity", lastLatency: null };
const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}
function when(t) { return t ? new Date(t * 1000).toLocaleTimeString() : ""; }
function ago(t) {
  if (!t) return "no events yet";
  const s = Math.max(0, Date.now() / 1000 - t);
  return s < 60 ? `${Math.round(s)} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
}
function where(m) { return m === "mac" ? "Mac" : m === "cowork-vm" ? "Cowork VM" : (m || "?"); }
function badge(state) { return el("span", `badge s-${state}`, state === "unknown-remote" ? "unknown (other machine)" : state); }
async function get(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

function shotData() { return S.data ? S.data.shots.find((s) => s.id === S.shot) : null; }

function renderShots() {
  const ul = $("shots");
  ul.replaceChildren();
  if (!S.data.shots.length) ul.append(el("li", "muted", "No shots with a state/ folder yet."));
  for (const s of S.data.shots) {
    const li = el("li", s.id === S.shot ? "on" : "");
    li.append(el("span", "", s.id === "." ? s.name : s.id));
    const c = s.counts || {};
    const bits = [ago(s.last)];
    if (c.running) bits.push(`${c.running} running`);
    if (c.FAIL || c.interrupted) bits.push(`${(c.FAIL || 0) + (c.interrupted || 0)} failed or interrupted`);
    li.append(el("span", "muted small", bits.join(" · ")));
    li.onclick = () => { S.shot = s.id; render(); };
    ul.append(li);
  }
  $("root").textContent = `Watching ${S.data.root}`;
}

function rows(s) {
  // merge ops (derived) and notes/snapshots into one list, newest first
  const out = s.ops.map((o) => ({ t: o.t, kind: "op", o }));
  for (const e of s.events) {
    if (e.kind === "note" || e.kind === "snapshot") out.push({ t: e.t, kind: e.kind, e });
  }
  return out.sort((a, b) => b.t - a.t).slice(0, 200);
}

function renderActivity() {
  const s = shotData();
  const tb = $("ops").querySelector("tbody");
  tb.replaceChildren();
  if (!s) return;
  if (s.bad_lines) {
    const tr = el("tr");
    const td = el("td", "warn", `${s.bad_lines} log line(s) failed their checksum and were ignored.`);
    td.colSpan = 5; tr.append(td); tb.append(tr);
  }
  for (const r of rows(s)) {
    const tr = el("tr");
    tr.append(el("td", "muted small", when(r.t)));
    if (r.kind === "op") {
      tr.append(el("td", "", r.o.op));
      const td = el("td"); td.append(badge(r.o.state)); tr.append(td);
      tr.append(el("td", "muted small", r.o.dur !== undefined && r.o.dur !== null ? `${r.o.dur} s` : ""));
      tr.append(el("td", "muted small", where(r.o.machine)));
      tr.onclick = () => showOp(r.o);
    } else if (r.kind === "note") {
      tr.append(el("td", "", r.e.summary || ""));
      const td = el("td"); td.append(badge(r.e.status || "note")); tr.append(td);
      tr.append(el("td", "muted small", r.e.source || ""));
      tr.append(el("td", "muted small", where(r.e.machine)));
      tr.onclick = () => showObj("Note", r.e);
    } else {
      const ch = r.e.prev ? ` (+${r.e.added ?? "?"} −${r.e.removed ?? "?"})` : " (first version)";
      tr.append(el("td", "", `script recorded: ${r.e.label}${ch}`));
      const td = el("td"); td.append(badge("note")); tr.append(td);
      tr.append(el("td", "muted small", `${Math.round((r.e.size || 0) / 1024)} KB`));
      tr.append(el("td", "muted small", where(r.e.machine)));
      tr.onclick = () => showSnapshot(r.e);
    }
    tb.append(tr);
  }
}

function kv(box, k, v) {
  if (v === undefined || v === null || (Array.isArray(v) && !v.length)) return;
  box.append(el("div", "muted small", k));
  box.append(el("pre", "", typeof v === "string" ? v : JSON.stringify(v, null, 1)));
}
function showObj(title, obj) {
  const d = $("detail"); d.replaceChildren(el("h3", "", title)); d.classList.remove("hidden");
  for (const [k, v] of Object.entries(obj)) if (!["crc", "v"].includes(k)) kv(d, k, v);
}
function showOp(o) {
  const d = $("detail"); d.replaceChildren(el("h3", "", `${o.op}`)); d.classList.remove("hidden");
  const p = el("p"); p.append(badge(o.state)); p.append(el("span", "muted small", `  started ${when(o.t)} on ${where(o.machine)} (pid ${o.pid})`)); d.append(p);
  if (o.state === "interrupted") d.append(el("p", "warn", "This operation never wrote its end event. Its process is gone, so the result is not known and must not be treated as done."));
  if (o.state === "unknown-remote") d.append(el("p", "warn", "Started on another machine; this viewer cannot check that process. It will show as interrupted if its deadline passes."));
  kv(d, "summary", o.summary); kv(d, "errors", o.errors); kv(d, "outputs", o.outputs); kv(d, "command", o.args);
}
async function showSnapshot(e) {
  const d = $("detail"); d.replaceChildren(el("h3", "", `Script: ${e.label}`)); d.classList.remove("hidden");
  d.append(el("p", "muted small", `${e.path} · sha ${e.sha} · ${e.size} bytes${e.stored ? "" : " · not stored (" + (e.detail || "") + ")"}`));
  if (!e.stored) return;
  try {
    if (e.prev) {
      const r = await get(`/api/diff?shot=${encodeURIComponent(S.shot)}&a=${e.prev}&b=${e.sha}`);
      const pre = el("pre");
      for (const ln of r.lines) {
        const cls = ln.startsWith("@@") ? "hunk" : ln.startsWith("+") ? "add" : ln.startsWith("-") ? "del" : "";
        pre.append(el("span", cls, ln + "\n"));
      }
      if (!r.lines.length) pre.textContent = "No changes since the previous version.";
      d.append(el("div", "muted small", "Changes since the previous recorded version")); d.append(pre);
    } else {
      const r = await get(`/api/snapshot?shot=${encodeURIComponent(S.shot)}&sha=${e.sha}`);
      d.append(el("div", "muted small", "First recorded version")); d.append(el("pre", "", r.text));
    }
  } catch (err) { d.append(el("p", "warn", `Could not load the script (${err.message}).`)); }
}

async function renderUnrecorded() {
  const box = $("unrecorded"); box.replaceChildren(el("p", "muted", "Checking…"));
  if (!S.shot) return;
  try {
    const r = await get(`/api/scan?shot=${encodeURIComponent(S.shot)}`);
    box.replaceChildren();
    if (!r.since) { box.append(el("p", "muted", "No events yet, so there is nothing to compare against.")); return; }
    box.append(el("p", "small", `${r.count} unrecorded change(s) since ${new Date(r.since * 1000).toLocaleString()} · ${r.scanned} files checked${r.truncated ? " (stopped at the limit)" : ""}`));
    const t = el("table"); const tb = el("tbody");
    for (const f of r.files) {
      const tr = el("tr"); tr.append(el("td", "", f.path)); tr.append(el("td", "muted small", new Date(f.mtime * 1000).toLocaleString()));
      tr.append(el("td", "muted small", `${Math.round(f.size / 1024)} KB`)); tb.append(tr);
    }
    t.append(tb); box.append(t);
  } catch (err) { box.replaceChildren(el("p", "warn", `Scan failed (${err.message}).`)); }
}

async function renderImages() {
  const g = $("images"); g.replaceChildren();
  if (!S.shot) return;
  try {
    const list = await get(`/api/images?shot=${encodeURIComponent(S.shot)}`);
    if (!list.length) g.append(el("p", "muted", "No review images yet."));
    for (const im of list) {
      const f = el("figure"); const img = el("img"); img.loading = "lazy"; img.alt = im.path;
      img.src = `/api/image?shot=${encodeURIComponent(S.shot)}&path=${encodeURIComponent(im.path)}`;
      f.append(img); f.append(el("figcaption", "", `${im.path} · ${new Date(im.mtime * 1000).toLocaleString()}`)); g.append(f);
    }
  } catch (err) { g.append(el("p", "warn", `Could not list images (${err.message}).`)); }
}

function renderMachines() {
  const box = $("machines"); box.replaceChildren();
  const pre = S.data.preflight || {};
  if (!Object.keys(pre).length) box.append(el("p", "muted", "No preflight reports yet. Run vfx.py preflight --root <folder> on each machine."));
  for (const [name, rep] of Object.entries(pre)) {
    const c = el("div", "card");
    c.append(el("h3", "", `${where(name)} · ${rep.ok ? "ready" : "not ready"} · ${rep.time ? new Date(rep.time * 1000).toLocaleString() : ""}`));
    const t = el("table"); const tb = el("tbody");
    for (const it of rep.items || []) {
      const tr = el("tr"); tr.append(el("td", "", it.item));
      const td = el("td"); td.append(badge(it.status)); tr.append(td);
      tr.append(el("td", "muted small", typeof it.detail === "string" ? it.detail : JSON.stringify(it.detail)));
      tb.append(tr);
    }
    t.append(tb); c.append(t); box.append(c);
  }
}

function renderMetrics(m) {
  if (!m) return;
  const bits = [];
  if (m.cpu_pct_60s !== null && m.cpu_pct_60s !== undefined) bits.push(`viewer CPU ${m.cpu_pct_60s}% (60 s)`);
  if (m.latency_p95_s !== null && m.latency_p95_s !== undefined) bits.push(`update delay p95 ${m.latency_p95_s} s`);
  if (S.lastLatency !== null) bits.push(`last event shown ${S.lastLatency.toFixed(2)} s after it was written`);
  $("metrics").textContent = bits.join(" · ");
}

function render() {
  if (!S.data) return;
  if (!S.shot && S.data.shots.length) S.shot = S.data.shots[0].id;
  renderShots();
  if (S.tab === "activity") renderActivity();
  if (S.tab === "unrecorded") renderUnrecorded();
  if (S.tab === "images") renderImages();
  if (S.tab === "machines") renderMachines();
  renderMetrics(S.data.metrics);
}

async function refresh() {
  try { S.data = await get("/api/state"); render(); }
  catch (err) { $("conn").textContent = err.message === "401" ? "signed out: reopen the Terminal link" : "viewer stopped"; $("conn").className = "conn off"; }
}

let pending = null;
function connect() {
  const es = new EventSource("/api/stream");
  es.onopen = () => { $("conn").textContent = "live"; $("conn").className = "conn on"; };
  es.onerror = () => { $("conn").textContent = "reconnecting"; $("conn").className = "conn off"; };
  const onMsg = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.event && m.event.t) S.lastLatency = Math.max(0, Date.now() / 1000 - m.event.t);
    clearTimeout(pending); pending = setTimeout(refresh, 150); // batch bursts into one refresh
  };
  es.addEventListener("event", onMsg);
  es.addEventListener("reload", onMsg);
}

for (const b of document.querySelectorAll(".tabs button")) {
  b.onclick = () => {
    S.tab = b.dataset.tab;
    for (const x of document.querySelectorAll(".tabs button")) x.classList.toggle("on", x === b);
    for (const x of document.querySelectorAll(".tab")) x.classList.toggle("on", x.id === `tab-${S.tab}`);
    render();
  };
}
setInterval(async () => { try { renderMetrics(await get("/api/health")); } catch (e) { /* refresh() reports */ } }, 5000);
refresh();
connect();
