// VFX Studio viewer. Read-only: every request is a GET and all data is shown with textContent.
"use strict";
const S = { data: null, shot: null, view: "overview", mode: null, lastSeq: null, seenAlerts: new Set(), notify: false };
const $ = (id) => document.getElementById(id);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked: keep in memory */ } },
};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}
function add(parent, ...kids) { for (const k of kids) if (k) parent.append(k); return parent; }
const vfx = () => S.mode === "vfx-artist";
const G = () => (S.data && S.data.glossary) || { ops: {}, states: {}, stages: {} };
function clock(t) { return t ? new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""; }
function ago(t) {
  if (!t) return "never";
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(t * 1000).toLocaleDateString();
}
function where(m) { return m === "mac" ? "Mac" : m === "cowork-vm" ? "Cowork VM" : m === "linux" ? "Linux machine" : m === "windows" ? "Windows PC" : (m || "unknown machine"); }
const ENGINE_SOURCES = new Set(["preflight", "selftest", "snapshot"]);  // notes the engine itself wrote
const CHECK_WORDS = { PASS: "OK", FAIL: "Problem", UNKNOWN: "Not found", NOT_APPLICABLE: "Not needed here" };
function opInfo(op) {
  const g = G().ops;
  return g[op] || g[(op || "").split(" ")[0]] || { title: `Technical step: ${op}`, what: "No plain-language description yet.", effect: "", manual: "" };
}
const CLS = { PASS: "st-ok", FAIL: "st-bad", interrupted: "st-bad", UNKNOWN: "st-warn", "unknown-remote": "st-warn",
  running: "st-run", NOT_APPLICABLE: "st-na", note: "st-na" };
function status(state, override) {
  const words = vfx() ? state : (G().states[state] || state);
  return el("span", `status ${CLS[state] || "st-na"}`, override || words);
}
async function get(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}
const shot = () => (S.data ? S.data.shots.find((s) => s.id === S.shot) : null);
const q = (s) => encodeURIComponent(s);

// ---------- items: ops (engine records) + notes and script versions ----------
function items(s) {
  const out = s.ops.map((o) => ({ t: o.t, kind: "op", o }));
  for (const e of s.events) if (e.kind === "note" || e.kind === "snapshot") out.push({ t: e.t, kind: e.kind, e });
  return out.sort((a, b) => b.t - a.t);
}
function itemTitle(it) {
  if (it.kind === "op") return it.o.title || opInfo(it.o.op).title;
  if (it.kind === "note" && it.e.source === "preflight") return `${opInfo("preflight").title} (${(it.e.summary || "").replace("preflight on ", "")})`;
  if (it.kind === "snapshot") return it.e.title || `${opInfo("snapshot").title}: ${it.e.label}`;
  return it.e.title || it.e.summary || "Note";
}
function itemRow(it, compact) {
  const li = el("li");
  add(li, el("div", "time", clock(it.t)));
  const mid = el("div");
  add(mid, el("div", "title", itemTitle(it)));
  if (it.kind === "op") {
    const bits = [where(it.o.machine)];
    if (it.o.dur !== undefined && it.o.dur !== null) bits.push(`${it.o.dur} s`);
    if (it.o.component) bits.push(it.o.component);
    mid.append(add(el("div", "meta"), el("span", "who", "Engine record · "), document.createTextNode(bits.join(" · "))));
    if (vfx() && !compact) mid.append(el("div", "cmd", `vfx.py ${(it.o.args || []).join(" ")}`));
    li.append(mid, status(it.o.state));
  } else if (it.kind === "snapshot") {
    const ch = it.e.prev ? `+${it.e.added ?? "?"} / −${it.e.removed ?? "?"} lines since last version` : "first version";
    mid.append(add(el("div", "meta"), el("span", "who", "Engine record · "), document.createTextNode(`${ch} · ${where(it.e.machine)}`)));
    li.append(mid, it.e.stored === false ? status("UNKNOWN", "Not stored") : status("NOT_APPLICABLE", "Saved"));
  } else if (ENGINE_SOURCES.has(it.e.source)) {
    mid.append(add(el("div", "meta"), el("span", "who", "Engine record · "), document.createTextNode(where(it.e.machine))));
    li.append(mid, it.e.status ? status(it.e.status) : el("span"));
  } else {
    mid.append(add(el("div", "meta"), el("span", "who note", "Note from Claude, not verified · "),
      document.createTextNode(where(it.e.machine))));
    if (it.e.title && it.e.summary && !compact) mid.append(el("div", "meta", it.e.summary));
    li.append(mid, el("span", "who note", it.e.status ? `says ${it.e.status}` : ""));
  }
  li.onclick = () => explain(it);
  return li;
}

// ---------- Explain this change ----------
function section(box, label, text, unknown) {
  add(box, el("h3", "", label), el("p", text ? "" : "unknown", text || unknown));
}
function openDrawer() { $("drawer").classList.remove("hidden"); return $("drawer-body"); }
async function explain(it) {
  const d = openDrawer(); d.replaceChildren(); d.className = "ex";
  const opname = it.kind === "op" ? it.o.op : it.kind;
  const info = opInfo(opname);
  add(d, el("div", "faint small", it.kind === "note" ? "Note from Claude, not a verified engine result" : "Explain this change"));
  add(d, el("h1", "", itemTitle(it)));
  const src = it.o || it.e;
  const st = it.kind === "op" ? status(it.o.state) : it.kind === "snapshot" ? status("NOT_APPLICABLE", "Script saved") : null;
  if (st) d.append(add(el("p"), st, el("span", "faint small", `   ${new Date(it.t * 1000).toLocaleString()} on ${where(src.machine)}`)));
  if (it.kind === "op" && it.o.state === "interrupted")
    d.append(el("p", "st-warn", "This step never reported that it finished and its process is gone. Treat the result as unknown, not done."));
  if (it.kind === "op" && it.o.state === "unknown-remote")
    d.append(el("p", "st-warn", "Started on another machine. This viewer can't check that process yet."));
  if (it.kind === "note") section(d, "What Claude said", src.summary, "");
  else section(d, "What happened", info.what, "");
  section(d, "Why", src.purpose, "Not recorded. Claude didn't give a reason for this step.");
  section(d, "What it touches in Blender", src.component, "Not recorded for this step.");
  if (it.kind !== "note") {
    section(d, "Effect on the picture", info.effect, "Not recorded.");
    section(d, "Do it yourself", info.manual, "No manual equivalent.");
  }
  if (it.kind === "op" && it.o.errors && it.o.errors.length) section(d, "What went wrong", it.o.errors.join("\n"), "");
  if (it.kind === "snapshot") await codeChange(d, it.e);
  const det = add(el("details"), el("summary", "", "Technical details"));
  if (vfx()) det.open = true;
  if (it.kind === "op") {
    det.append(el("div", "faint small", "Command"), el("pre", "", `vfx.py ${(it.o.args || []).join(" ")}`));
    if (it.o.summary) det.append(el("div", "faint small", "Result"), el("pre", "", JSON.stringify(it.o.summary, null, 1)));
    if (it.o.outputs) det.append(el("div", "faint small", "Outputs"), el("pre", "", it.o.outputs.join("\n")));
    det.append(el("div", "faint small", "Record"), el("pre", "", `op ${it.o.op}\nid ${it.o.op_id}\npid ${it.o.pid}\nhost ${it.o.host}`));
  } else {
    const raw = Object.assign({}, src); delete raw.crc;
    det.append(el("pre", "", JSON.stringify(raw, null, 1)));
  }
  d.append(det);
}
async function codeChange(d, e) {
  add(d, el("h3", "", "Code change"));
  if (e.stored === false) { d.append(el("p", "unknown", `Not stored: ${e.detail || "too large or not text"}.`)); return; }
  d.append(el("p", "", e.prev ? `${e.added ?? "?"} lines added, ${e.removed ?? "?"} removed since the previous version of ${e.label}.` : `First recorded version of ${e.label}.`));
  const box = el("div");
  const btn = el("button", "btn", "Show the code change");
  let shown = false;
  const toggle = async () => {
    shown = !shown; btn.textContent = shown ? "Hide code" : "Show the code change"; box.replaceChildren();
    if (!shown) return;
    try {
      if (e.prev) {
        const r = await get(`/api/diff?shot=${q(S.shot)}&a=${e.prev}&b=${e.sha}`);
        const pre = el("pre");
        for (const ln of r.lines) pre.append(el("span", ln.startsWith("@@") ? "hunk" : ln.startsWith("+") ? "add" : ln.startsWith("-") ? "del" : "", ln + "\n"));
        if (!r.lines.length) pre.textContent = "No changes.";
        box.append(pre);
      } else {
        const r = await get(`/api/snapshot?shot=${q(S.shot)}&sha=${e.sha}`);
        box.append(el("pre", "", r.text));
      }
    } catch (err) { box.append(el("p", "st-warn", `Could not load the code (${err.message}).`)); }
  };
  btn.onclick = toggle;
  d.append(btn, box);
  if (vfx()) toggle();
}

// ---------- dials ----------
function dial(label, pct, valueText, note, tone, off) {
  const box = el("div", `dial${off ? " off" : ""}`);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", "0 0 100 100"); svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${label}: ${valueText}`);
  const ring = (stroke, frac) => {
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", "50"); c.setAttribute("cy", "50"); c.setAttribute("r", "40"); c.setAttribute("fill", "none");
    c.setAttribute("stroke", stroke); c.setAttribute("stroke-width", "8"); c.setAttribute("stroke-linecap", "round");
    c.setAttribute("transform", "rotate(135 50 50)");
    const full = 2 * Math.PI * 40; c.setAttribute("stroke-dasharray", `${frac * full * 0.75} ${full}`);
    return c;
  };
  svg.append(ring("#2a2d33", 1));
  const col = { ok: "#3fb950", warn: "#e0a43a", bad: "#f2555a", neutral: "#5b9cf8" }[tone] || "#5b9cf8";
  if (pct !== null && pct !== undefined && !off) svg.append(ring(col, Math.max(0.01, Math.min(1, pct / 100))));
  const t = document.createElementNS(ns, "text"); t.setAttribute("x", "50"); t.setAttribute("y", "56"); t.setAttribute("text-anchor", "middle");
  t.setAttribute("fill", off ? "#6b707a" : "#e7e7ea"); t.setAttribute("font-size", valueText.length > 6 ? "13" : "18"); t.setAttribute("font-weight", "600");
  t.textContent = valueText; svg.append(t);
  add(box, svg, el("div", "lbl", label), el("div", "note", note || ""));
  return box;
}
function dialsFor(tel, mini) {
  const wrap = el("div", mini ? "dials mini" : "dials");
  const off = (r) => !r || !r.available;
  const why = (r) => (r && r.why) || "not available";
  const c = tel.cpu, g = tel.gpu, m = tel.memory, p = tel.pressure, sw = tel.swap, dk = tel.disk, th = tel.thermal;
  wrap.append(off(c) ? dial("CPU", null, "n/a", mini ? "" : why(c), "off", true)
    : dial("CPU", c.busy_pct, `${Math.round(c.busy_pct)}%`, mini ? "" : `whole machine, ${c.cores} cores`, "neutral"));
  wrap.append(off(g) ? dial("GPU", null, "n/a", mini ? "" : why(g), "off", true)
    : dial("GPU", g.busy_pct, `${g.busy_pct}%`, mini ? "" : "busy (high is normal while rendering)", "neutral"));
  if (off(m)) wrap.append(dial("Memory", null, "n/a", mini ? "" : why(m), "off", true));
  else {
    const tone = p && p.available ? (p.level === "critical" ? "bad" : p.level === "warning" ? "warn" : "ok") : "neutral";
    wrap.append(dial(m.unified ? "Unified memory" : "Memory", m.used_pct, `${m.used_gb}/${m.total_gb}`,
      mini ? "" : `GB used${m.unified ? ", shared by CPU and GPU" : ""}`, tone));
  }
  wrap.append(off(dk) ? dial("Storage", null, "n/a", mini ? "" : why(dk), "off", true)
    : dial("Free storage", dk.free_pct, `${Math.round(dk.free_gb)} GB`, mini ? "" : `${dk.free_pct}% free on the project drive`,
      dk.free_pct < 5 ? "bad" : dk.free_pct < 10 ? "warn" : "ok"));
  if (!mini) {
    wrap.append(off(p) ? dial("Memory pressure", null, "n/a", why(p), "off", true)
      : dial("Memory pressure", p.level === "normal" ? 20 : p.level === "warning" ? 60 : 95, p.level, "how hard the system works to find memory",
        p.level === "normal" ? "ok" : p.level === "warning" ? "warn" : "bad"));
    wrap.append(off(sw) ? dial("Swap", null, "n/a", why(sw), "off", true)
      : dial("Swap", sw.total_gb ? sw.used_pct : 0, `${sw.used_gb} GB`, sw.total_gb ? `of ${sw.total_gb} GB swap in use` : "no swap in use",
        sw.used_gb > 4 ? "warn" : "neutral"));
    wrap.append(off(th) ? dial("Thermal", null, "n/a", why(th), "off", true)
      : dial("Thermal", { nominal: 15, fair: 45, serious: 75, critical: 98 }[th.state] || 50, th.state, "temperature itself needs admin access",
        th.state === "nominal" || th.state === "fair" ? "ok" : th.state === "serious" ? "warn" : "bad"));
  }
  return wrap;
}

// ---------- views ----------
function viewOverview() {
  const v = $("view-overview"); v.replaceChildren();
  const s = shot();
  if (!s) { v.append(el("h1", "", "No shots yet"), el("p", "sub", "A shot appears here once it has been set up with the engine.")); return; }
  const ov = s.overview || {};
  const stage = ov.stage ? (G().stages[ov.stage] || ov.stage) : "Not set up";
  add(v, el("h1", "", s.name), el("p", "sub", `${stage} · ${ov.version ? `working version ${ov.version}` : "no working version yet"}`));
  const hero = el("div", "grid g-hero");
  const pic = add(el("div", "card"), el("h2", "", "Latest image"));
  const pv = el("div", "preview");
  if (ov.latest_image) {
    const img = el("img"); img.alt = ov.latest_image.path; img.src = `/api/image?shot=${q(s.id)}&path=${q(ov.latest_image.path)}&v=${ov.latest_image.mtime}`; pv.append(img);
    pic.append(pv, el("div", "faint small", `${ov.latest_image.path} · ${ago(ov.latest_image.mtime)}`));
  } else { pv.append(el("div", "empty", "No render or review image yet")); pic.append(pv); }
  const now = add(el("div", "card"), el("h2", "", "Right now"));
  if (ov.running && ov.running.length) for (const o of ov.running) now.append(el("div", "big", o.title || opInfo(o.op).title), status(o.state));
  else now.append(el("div", "big", "Nothing running"), el("p", "muted small", `Last activity ${ago(s.last)}`));
  now.append(el("h2", "", "Live Blender view"), add(el("p", "small muted"), el("span", "tag planned", "Planned"), document.createTextNode(" arrives with the Blender add-on")));
  now.append(el("h2", "", "Approvals"), add(el("p", "small muted"), el("span", "tag planned", "Not available yet"), document.createTextNode(" arrive with the production runner")));
  hero.append(pic, now); v.append(hero);

  const row = el("div", "grid g-4"); row.style.marginTop = "14px";
  const ready = add(el("div", "card click"), el("h2", "", "Ready to work"));
  const pre = S.data.preflight || {};
  if (!Object.keys(pre).length) ready.append(el("p", "muted small", "No readiness check yet"));
  for (const [n, r] of Object.entries(pre))
    ready.append(add(el("div", "rows"), add(el("div"), el("span", "", where(n)), status(r.ok ? "PASS" : "FAIL", r.ok ? "Ready" : "Not ready"))));
  ready.onclick = () => go("machine");
  const prob = add(el("div", "card click"), el("h2", "", "Problems"));
  const act = (S.data.alerts.active || []).filter((a) => a.sev !== "info" && (!a.shot || a.shot === s.id));
  if (!act.length) prob.append(el("p", "st-ok small", "No active problems"));
  for (const a of act.slice(0, 3)) prob.append(add(el("p", "small"), status(a.sev === "critical" ? "FAIL" : "UNKNOWN", a.title)));
  prob.onclick = () => go("alerts");
  const learn = add(el("div", "card"), el("h2", "", "Learning and research"));
  const st = S.data.settings || {};
  learn.append(add(el("div", "rows"),
    add(el("div"), el("span", "", "Learning"), el("span", "", st.learning || "off")),
    add(el("div"), el("span", "", "Online research"), el("span", "", st.research || "off")),
    add(el("div"), el("span", "", "Budget"), el("span", "", st.budget || "balanced"))));
  const mach = add(el("div", "card click"), el("h2", "", `${where(S.data.machine)} now`));
  const md = el("div"); md.id = "ov-dials";
  md.append(S.data.telemetry ? dialsFor(S.data.telemetry, true) : el("p", "muted small", "Readings start when this page is open"));
  mach.append(md);
  mach.onclick = () => go("machine");
  row.append(ready, prob, learn, mach); v.append(row);

  const recent = add(el("div", "card"), el("h2", "", "Recent changes")); recent.style.marginTop = "14px";
  const ul = el("ul", "timeline compact");
  for (const it of items(s).slice(0, 7)) ul.append(itemRow(it, true));
  if (!ul.children.length) recent.append(el("p", "muted small", "Nothing yet"));
  recent.append(ul); v.append(recent);
}

function viewActivity() {
  const v = $("view-activity"); v.replaceChildren();
  add(v, el("h1", "", "Activity"), el("p", "sub", vfx() ? "Engine records and agent notes, newest first. Click one for the command, result and code." :
    "Everything done on this shot, newest first. Click a step to see what changed and why."));
  const s = shot(); if (!s) return;
  if (s.bad_lines) v.append(el("p", "st-warn small", `${s.bad_lines} damaged log line(s) were ignored.`));
  const ul = el("ul", "timeline");
  for (const it of items(s).slice(0, 200)) ul.append(itemRow(it, false));
  v.append(add(el("div", "card"), ul));
}

async function viewImages() {
  const v = $("view-images"); v.replaceChildren(el("h1", "", "Images"), el("p", "sub", "Newest review images and frames named by engine steps."));
  const s = shot(); if (!s) return;
  try {
    const list = await get(`/api/images?shot=${q(s.id)}`);
    const g = el("div", "gallery");
    if (!list.length) v.append(el("div", "card empty", "No review images yet. They appear when a render or contact sheet is written to the shot's _review folder."));
    for (const im of list) {
      const f = el("figure"); const img = el("img"); img.loading = "lazy"; img.alt = im.path;
      img.src = `/api/image?shot=${q(s.id)}&path=${q(im.path)}&v=${im.mtime}`;
      f.append(img, el("figcaption", "", `${im.path.split("/").pop()} · ${ago(im.mtime)}`));
      f.onclick = () => {
        const d = openDrawer(); d.className = ""; d.replaceChildren(el("h1", "", im.path.split("/").pop()));
        const big = el("img"); big.src = img.src; big.alt = im.path; big.style.width = "100%"; d.append(big, el("p", "faint small", im.path));
      };
      g.append(f);
    }
    v.append(g);
  } catch (err) { v.append(el("p", "st-warn", `Could not list images (${err.message}).`)); }
}

const LABELS = { engine: "VFX engine", machine: "Computer", blender: "Blender", python_modules: "Image tools", ffmpeg: "Video tools",
  state_write_test: "Saving shot records", shot_events: "Shot log", personal_overrides: "Your profile", settings: "Settings", hardware: "Hardware" };
function viewMachine() {
  const v = $("view-machine"); v.replaceChildren();
  const tel = S.data.telemetry, here = where(S.data.machine);
  add(v, el("h1", "", "Machine"), el("p", "sub", `Live readings from this ${here}, the computer running this viewer. Updated every ${S.data.metrics.telemetry_every_s} s while this page is open.`));
  if (!tel) v.append(el("div", "card empty", "No readings yet. They start a few seconds after the page opens."));
  else {
    v.append(dialsFor(tel, false));
    const g2 = el("div", "grid g-2"); g2.style.marginTop = "14px";
    const wl = add(el("div", "card"), el("h2", "", "Blender and processing"));
    const w = tel.workloads;
    if (!w || !w.available) wl.append(el("p", "muted small", (w && w.why) || "not available"));
    else if (!w.processes.length) wl.append(el("p", "muted small", "Nothing running: no Blender, ffmpeg or engine processes"));
    else for (const p of w.processes) wl.append(add(el("div", "rows"), add(el("div"), el("span", "", `${p.role} (${p.name})`),
      el("span", "", `${Math.round(p.cpu_pct_of_one_core)}% of one core · ${p.rss_mb} MB`))));
    const me = add(el("div", "card"), el("h2", "", "This viewer"));
    const m = S.data.metrics;
    me.append(add(el("div", "rows"),
      add(el("div"), el("span", "", "CPU (viewer plus its readings)"), el("span", "", tel.studio.cpu_pct !== undefined ? `${tel.studio.cpu_pct}%` : "measuring")),
      add(el("div"), el("span", "", "Memory"), el("span", "", tel.studio.rss_mb ? `${tel.studio.rss_mb} MB` : "n/a")),
      add(el("div"), el("span", "", "Cost of one reading"), el("span", "", `${tel.sample_cpu_s} s CPU`)),
      add(el("div"), el("span", "", "Update delay (p95)"), el("span", "", m.latency_p95_s !== null ? `${m.latency_p95_s} s` : "no events yet"))));
    if (vfx() && tel.gpu && tel.gpu.available) me.append(el("p", "faint small", `GPU: ${tel.gpu.method}; unified memory used by the GPU: ${tel.gpu.unified_memory_in_use_gb} GB`));
    if (vfx() && tel.memory && tel.memory.method) me.append(el("p", "faint small", `Memory: ${tel.memory.method}`));
    g2.append(wl, me); v.append(g2);
  }
  const pre = S.data.preflight || {};
  const g = el("div", "grid g-2"); g.style.marginTop = "14px";
  for (const [n, r] of Object.entries(pre)) {
    const c = add(el("div", "card"), el("h2", "", `${where(n)} readiness · checked ${ago(r.time)}`));
    if (n !== S.data.machine) c.append(el("p", "faint small", n === "cowork-vm" ? "No live readings: the Cowork VM only runs while Claude works. This is its last check." : "Last check from that machine."));
    const rows = el("div", "rows");
    for (const it of r.items || []) {
      const d = it.detail;
      const detail = typeof d === "string" ? d : it.item === "blender" ? d.version : it.item === "engine" ? `${d.version} (${d.commit})` : "";
      rows.append(add(el("div"), el("span", "", LABELS[it.item] || it.item),
        add(el("span"), status(it.status, vfx() ? null : CHECK_WORDS[it.status]), vfx() && detail ? el("span", "faint small", `  ${detail}`) : null)));
    }
    c.append(rows); g.append(c);
  }
  v.append(g);
}

async function viewChanges() {
  const v = $("view-changes"); v.replaceChildren(el("h1", "", "Outside changes"),
    el("p", "sub", "Files in this shot that changed with no engine step to explain them, for example edits made directly in Blender or by hand. They may be fine, but nothing has checked them."));
  const s = shot(); if (!s) return;
  try {
    const r = await get(`/api/scan?shot=${q(s.id)}`);
    if (!r.since) { v.append(el("div", "card empty", "Nothing recorded yet, so there is nothing to compare against.")); return; }
    const c = el("div", "card");
    c.append(el("p", r.count ? "st-warn" : "st-ok", r.count ? `${r.count} unexplained change(s) since ${new Date(r.since * 1000).toLocaleString()}` : `No unexplained changes. ${r.scanned} files checked.`));
    const rows = el("div", "rows");
    for (const f of r.files) rows.append(add(el("div"), el("span", "", f.path), el("span", "", `${ago(f.mtime)} · ${Math.max(1, Math.round(f.size / 1024))} KB`)));
    c.append(rows); v.append(c);
  } catch (err) { v.append(el("p", "st-warn", `Check failed (${err.message}).`)); }
}

function viewAlerts() {
  const v = $("view-alerts"); v.replaceChildren();
  const a = S.data.alerts;
  add(v, el("h1", "", "Alerts"), el("p", "sub", "One alert per problem, kept until it clears. Finished renders show for 10 minutes."));
  const btn = el("button", "btn", S.notify ? "Desktop notifications: on (click to turn off)" : "Turn on desktop notifications");
  btn.onclick = async () => {
    if (!("Notification" in window)) { btn.textContent = "This browser has no notifications"; return; }
    if (S.notify) { S.notify = false; store.set("vfx.notify", "0"); viewAlerts(); return; }
    const p = await Notification.requestPermission();
    S.notify = p === "granted"; store.set("vfx.notify", S.notify ? "1" : "0"); viewAlerts();
  };
  v.append(btn);
  const c = add(el("div", "card"), el("h2", "", "Active")); c.style.marginTop = "14px";
  if (!a.active.length) c.append(el("p", "st-ok small", "Nothing needs attention"));
  for (const x of a.active) c.append(alertRow(x));
  const r = add(el("div", "card"), el("h2", "", "Recently cleared")); r.style.marginTop = "14px";
  if (!a.recent.length) r.append(el("p", "muted small", "None"));
  for (const x of a.recent) r.append(alertRow(x));
  const n = add(el("div", "card"), el("h2", "", "Not monitored yet")); n.style.marginTop = "14px";
  for (const x of a.not_monitored) n.append(el("p", "muted small", x));
  v.append(c, r, n);
}
function alertRow(x) {
  const state = !x.active ? "NOT_APPLICABLE" : x.sev === "critical" ? "FAIL" : x.sev === "warning" ? "UNKNOWN" : "PASS";
  const row = el("div", "alert");
  add(row, status(state, x.active ? x.sev : "cleared"), add(el("div"), el("div", "title", x.title), el("div", "meta muted small", x.detail || "")),
    el("div", "faint small", `${x.count > 1 ? `${x.count}× · ` : ""}${ago(x.last)}`));
  return row;
}

// ---------- shell ----------
function renderChrome() {
  const sel = $("shot");
  sel.replaceChildren(...S.data.shots.map((s) => { const o = el("option", "", s.id); o.value = s.id; return o; }));
  if ((!S.shot || !S.data.shots.some((s) => s.id === S.shot)) && S.data.shots.length) S.shot = S.data.shots[0].id;
  sel.value = S.shot || "";
  for (const b of document.querySelectorAll(".mode button")) b.classList.toggle("on", b.dataset.mode === S.mode);
  const act = S.data.alerts.active.filter((a) => a.sev !== "info");
  $("bell-count").textContent = String(act.length);
  $("bell").classList.toggle("has-warn", act.some((a) => a.sev === "warning"));
  $("bell").classList.toggle("has-crit", act.some((a) => a.sev === "critical"));
  $("foot").textContent = `Read-only viewer · engine ${S.data.version} · ${where(S.data.machine)}`;
}
function render() {
  if (!S.data) return;
  renderChrome();
  ({ overview: viewOverview, activity: viewActivity, images: viewImages, machine: viewMachine, changes: viewChanges, alerts: viewAlerts })[S.view]();
}
function go(view) {
  S.view = view;
  for (const b of document.querySelectorAll(".side button")) b.classList.toggle("on", b.dataset.view === view);
  for (const x of document.querySelectorAll(".view")) x.classList.toggle("on", x.id === `view-${view}`);
  render();
}
function notifyNew(alerts) {
  const first = S.seenAlerts.size === 0 && S.lastSeq === null;
  for (const a of alerts.active) {
    const k = `${a.key}#${a.count}`;
    if (S.seenAlerts.has(k)) continue;
    S.seenAlerts.add(k);
    if (!first && S.notify && document.hidden && "Notification" in window && Notification.permission === "granted")
      new Notification(a.title, { body: a.detail || "" });
  }
}
async function refresh() {
  try {
    const data = await get("/api/state");
    notifyNew(data.alerts);
    S.data = data;
    S.lastSeq = data.seq;
    if (!S.mode) S.mode = S.hash.mode || store.get("vfx.mode") || (data.settings && data.settings.mode) || "filmmaker";
    if (S.hash.view && !S.hashDone) { S.hashDone = true; go(S.hash.view); openFromHash(); return; }
    render();
  } catch (err) {
    $("conn").textContent = err.message === "401" ? "Signed out: use the Terminal link" : "Viewer stopped";
    $("conn").className = "pill off";
  }
}
let pending = null;
function soon() { clearTimeout(pending); pending = setTimeout(refresh, 150); }
function connect() {
  const es = new EventSource("/api/stream");
  let wasDown = false;
  es.onopen = () => { $("conn").textContent = "Live"; $("conn").className = "pill on"; if (wasDown) refresh(); wasDown = false; };
  es.onerror = () => { $("conn").textContent = "Reconnecting"; $("conn").className = "pill off"; wasDown = true; };
  const handle = (ev) => {
    const m = JSON.parse(ev.data);
    const gap = S.lastSeq !== null && m.seq > S.lastSeq + 1;
    if (m.seq > (S.lastSeq || 0)) S.lastSeq = m.seq;
    if (gap || m.type === "event" || m.type === "reload") { soon(); return; }  // missed a message: catch up from /api/state
    if (m.type === "telemetry" && S.data) {
      S.data.telemetry = m.telemetry;
      if (S.view === "machine") render();
      else if (S.view === "overview" && $("ov-dials")) $("ov-dials").replaceChildren(dialsFor(m.telemetry, true));
    }
    if (m.type === "alerts" && S.data) { notifyNew(m.alerts); S.data.alerts = m.alerts; renderChrome(); if (S.view === "alerts" || S.view === "overview") render(); }
  };
  for (const t of ["event", "reload", "telemetry", "alerts", "error"]) es.addEventListener(t, handle);
}

// Links like #view=activity&mode=vfx-artist&shot=benchmarks/iris&open=snapshot open a screen directly.
S.hash = Object.fromEntries(new URLSearchParams(location.hash.slice(1)));
if (S.hash.shot) S.shot = S.hash.shot;
if (S.hash.mode === "filmmaker" || S.hash.mode === "vfx-artist") S.mode = S.hash.mode; else delete S.hash.mode;
if (!["overview", "activity", "images", "machine", "changes", "alerts"].includes(S.hash.view)) delete S.hash.view;
function openFromHash() {
  const s = shot(); if (!s || !S.hash.open) return;
  const it = items(s).find((x) => x.kind === S.hash.open || (x.kind === "op" && x.o.op === S.hash.open));
  if (it) explain(it);
}
for (const b of document.querySelectorAll(".side button")) b.onclick = () => go(b.dataset.view);
for (const b of document.querySelectorAll(".mode button")) b.onclick = () => { S.mode = b.dataset.mode; store.set("vfx.mode", S.mode); render(); };
$("shot").onchange = (e) => { S.shot = e.target.value; render(); };
$("bell").onclick = () => go("alerts");
$("drawer-close").onclick = () => $("drawer").classList.add("hidden");
S.notify = store.get("vfx.notify") === "1";
setInterval(refresh, 30000);  // safety net if a stream message was lost
refresh();
connect();
