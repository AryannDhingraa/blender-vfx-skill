"""Find free assets through supported APIs, rank them for the shot and the
machine, show them for approval, and download only after a yes.

Sources (both CC0, no account needed):
  Poly Haven  https://api.polyhaven.com   models, textures, HDRIs
  ambientCG   https://ambientcg.com/api/v2 materials (PBR texture sets)
"""
import hashlib
import json
import math
import os
import re
import time
import urllib.request
import zipfile

from .common import atomic_write

UA = "blender-vfx-skill/2.0 (+https://github.com/AryannDhingraa/blender-vfx-skill)"
PH = "https://api.polyhaven.com"
ACG = "https://ambientcg.com/api/v2/full_json"
PH_TYPES = {"hdri": "hdris", "texture": "textures", "model": "models"}
RES_ORDER = ["1k", "2k", "4k", "8k", "16k"]
TEXTURE_MAPS = {"Diffuse": "diffuse", "Rough": "roughness", "nor_gl": "normal", "Displacement": "displacement",
                "arm": "arm", "AO": "ao", "Metal": "metallic"}


def _get(url, timeout=30, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # network errors vary by platform
            last = e
            time.sleep(1 + i)
    raise RuntimeError(f"could not fetch {url}: {last}")


def _json(url):
    return json.loads(_get(url).decode("utf-8"))


def _words(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1]


def _score(query_words, name, tags, cats, downloads):
    hay_name, hay_tags = set(_words(name)), set(_words(" ".join(tags + cats)))
    s = 0.0
    for w in query_words:
        if w in hay_name:
            s += 3
        elif w in hay_tags:
            s += 2
        elif any(h.startswith(w) or w.startswith(h) for h in hay_name | hay_tags if len(h) > 3):
            s += 1
    return s + math.log10(1 + (downloads or 0)) * 0.1 if s else 0.0


def _pick_res(available, wanted):
    avail = [r for r in RES_ORDER if r in available]
    if not avail:
        return None
    below = [r for r in avail if RES_ORDER.index(r) <= RES_ORDER.index(wanted)]
    return below[-1] if below else avail[0]


def suitability(kind, budget, polycount=None, max_res=None):
    notes, level = [], "good"
    if kind == "model" and polycount:
        if polycount > budget["poly_heavy"]:
            level = "too heavy"
            notes.append(f"{polycount:,} polygons is over this machine's {budget['poly_heavy']:,} limit; decimate or pick another")
        elif polycount > budget["poly_ok"]:
            level = "heavy"
            notes.append(f"{polycount:,} polygons: fine as a hero, too many to duplicate")
    if max_res and max_res < 2048 and kind != "hdri":
        notes.append("textures under 2k: background use only")
        level = "ok" if level == "good" else level
    return level, notes


def _ph_candidates(kind, words, budget, limit):
    d = _json(f"{PH}/assets?type={PH_TYPES[kind]}")
    scored = []
    for aid, a in d.items():
        s = _score(words, a.get("name", aid) + " " + aid, a.get("tags", []), a.get("categories", []),
                   a.get("download_count"))
        if s:
            scored.append((s, aid, a))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, aid, a in scored[:limit]:
        max_res = (a.get("max_resolution") or [0])[0]
        poly = a.get("polycount")
        level, notes = suitability(kind, budget, poly, max_res)
        out.append({"source": "polyhaven", "id": aid, "name": a.get("name", aid), "type": kind,
                    "licence": "CC0", "page": f"https://polyhaven.com/a/{aid}",
                    "thumbnail": (a.get("thumbnail_url") or f"https://cdn.polyhaven.com/asset_img/thumbs/{aid}.png?width=256&height=256").replace("format=webp", "format=png"),
                    "authors": list((a.get("authors") or {}).keys()), "max_res": f"{max_res // 1024}k" if max_res else None,
                    "polycount": poly, "size_m": [round(x / 1000, 2) for x in a["dimensions"]] if a.get("dimensions") else None,
                    "suggested_res": budget["texture_res"] if kind != "hdri" else ("2k" if budget["render_memory_gb"] <= 4 else "4k"),
                    "suitability": level, "notes": notes, "score": round(s, 2)})
    return out


def _acg_candidates(words, budget, limit):
    q = "+".join(words)
    d = _json(f"{ACG}?type=Material&q={q}&limit={max(limit * 3, 10)}&include=downloadData,imageData,tagData")
    out = []
    for a in d.get("foundAssets", []):
        s = _score(words, a.get("displayName", "") + " " + a["assetId"], a.get("tags", []) or [],
                   [a.get("category") or ""], a.get("downloadCount"))
        if not s:
            continue
        dl = a.get("downloadFolders", {}).get("default", {}).get("downloadFiletypeCategories", {}).get("zip", {}).get("downloads", [])
        res = sorted({x["attribute"].split("-")[0].lower() for x in dl if x.get("attribute", "").endswith("JPG")},
                     key=lambda r: RES_ORDER.index(r) if r in RES_ORDER else 99)
        level, notes = suitability("texture", budget, None, int(res[-1][:-1]) * 1024 if res and res[-1][:-1].isdigit() else None)
        out.append({"source": "ambientcg", "id": a["assetId"], "name": a.get("displayName", a["assetId"]),
                    "type": "texture", "licence": "CC0", "page": f"https://ambientcg.com/view?id={a['assetId']}",
                    "thumbnail": (a.get("previewImage") or {}).get("256-PNG"), "authors": ["ambientCG"],
                    "max_res": res[-1] if res else None, "method": a.get("creationMethodName"),
                    "suggested_res": _pick_res(res, budget["texture_res"]), "suitability": level, "notes": notes,
                    "score": round(s, 2)})
    out.sort(key=lambda c: -c["score"])
    return out[:limit]


def search(query, kind, budget, limit=5):
    if kind not in PH_TYPES:
        raise ValueError("type must be model, texture or hdri")
    words = _words(query)
    cands, errors = [], []
    try:
        cands += _ph_candidates(kind, words, budget, limit)
    except RuntimeError as e:
        errors.append(str(e))
    if kind == "texture":
        try:
            cands += _acg_candidates(words, budget, limit)
        except RuntimeError as e:
            errors.append(str(e))
    cands.sort(key=lambda c: (c["suitability"] == "too heavy", -c["score"]))
    cands = cands[:limit]
    for i, c in enumerate(cands, 1):
        c["option"] = i
        del c["score"]
    res = {"query": query, "type": kind, "options": cands, "budget": budget}
    if not cands:
        res["fallback"] = "no good match: build it procedurally (procedural_asset.py) or try other words"
    if errors:
        res["errors"] = errors
    return res


def contact_sheet(options, out_path, size=256):
    """One image with every option's thumbnail and number, for approval."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    tiles = []
    for c in options:
        img = None
        if c.get("thumbnail"):
            try:
                img = cv2.imdecode(np.frombuffer(_get(c["thumbnail"], timeout=20, retries=1), np.uint8), cv2.IMREAD_COLOR)
            except RuntimeError:
                img = None
        if img is None:
            img = np.full((size, size, 3), 40, np.uint8)
        img = cv2.resize(img, (size, size))
        bar = np.full((44, size, 3), 20, np.uint8)
        label = f"{c['option']}. {c['name'][:22]}"
        sub = " ".join(x for x in [c.get("max_res") or "", f"{c['polycount']:,}p" if c.get("polycount") else "",
                                   c["suitability"]] if x)
        cv2.putText(bar, label, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(bar, sub, (6, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (190, 190, 190), 1, cv2.LINE_AA)
        tiles.append(np.vstack([img, bar]))
    if not tiles:
        return None
    sheet = np.hstack(tiles)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cv2.imwrite(out_path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return out_path


def _fetch_to(url, path, md5=None, size=None):
    data = _get(url, timeout=120)
    if size is not None and len(data) != size:
        raise RuntimeError(f"{os.path.basename(path)}: got {len(data)} bytes, expected {size}")
    if md5 and hashlib.md5(data).hexdigest() != md5:
        raise RuntimeError(f"{os.path.basename(path)}: checksum mismatch")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)
    return len(data)


def _safe_extract(zpath, dest):
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            target = os.path.abspath(os.path.join(dest, n))
            if not target.startswith(os.path.abspath(dest) + os.sep):
                raise RuntimeError(f"unsafe path in zip: {n}")
        z.extractall(dest)
        return z.namelist()


def download(source, aid, kind, res, dest_root, approved=False, licence_log=None):
    if not approved:
        return {"status": "refused", "errors": ["show the options and get the user's yes first, then pass --approved"]}
    dest = os.path.join(dest_root, aid)
    files, total = {}, 0
    if source == "polyhaven":
        info = _json(f"{PH}/info/{aid}")
        tree = _json(f"{PH}/files/{aid}")
        if kind == "hdri":
            r = _pick_res(tree["hdri"], res)
            e = tree["hdri"][r].get("exr") or tree["hdri"][r]["hdr"]
            p = os.path.join(dest, os.path.basename(e["url"]))
            total += _fetch_to(e["url"], p, e.get("md5"), e.get("size"))
            files["hdri"] = p
        elif kind == "model":
            r = _pick_res(tree["gltf"], res)
            g = tree["gltf"][r]["gltf"]
            p = os.path.join(dest, os.path.basename(g["url"]))
            total += _fetch_to(g["url"], p, g.get("md5"), g.get("size"))
            for rel, inc in g.get("include", {}).items():
                total += _fetch_to(inc["url"], os.path.join(dest, rel), inc.get("md5"), inc.get("size"))
            files["model"] = p
        else:
            r = None
            for key, role in TEXTURE_MAPS.items():
                if key not in tree:
                    continue
                rr = _pick_res(tree[key], res)
                fmt = "exr" if role == "displacement" and "exr" in tree[key][rr] else "jpg"
                e = tree[key][rr].get(fmt) or next(iter(tree[key][rr].values()))
                p = os.path.join(dest, os.path.basename(e["url"]))
                total += _fetch_to(e["url"], p, e.get("md5"), e.get("size"))
                files[role] = p
                r = rr
        name, authors = info.get("name", aid), list((info.get("authors") or {}).keys())
        page = f"https://polyhaven.com/a/{aid}"
    elif source == "ambientcg":
        d = _json(f"{ACG}?id={aid}&include=downloadData")
        a = d["foundAssets"][0]
        dl = a["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
        jpgs = {x["attribute"].split("-")[0].lower(): x for x in dl if x["attribute"].endswith("JPG")}
        r = _pick_res(list(jpgs), res)
        x = jpgs[r]
        zp = os.path.join(dest, x["fileName"])
        total += _fetch_to(x["fullDownloadPath"], zp, None, x.get("size"))
        for n in _safe_extract(zp, dest):
            low = n.lower()
            for key, role in (("color", "diffuse"), ("roughness", "roughness"), ("normalgl", "normal"),
                              ("displacement", "displacement"), ("metalness", "metallic"), ("ambientocclusion", "ao")):
                if key in low and low.endswith((".jpg", ".png", ".exr")):
                    files[role] = os.path.join(dest, n)
        os.remove(zp)
        name, authors, page = a.get("displayName", aid), ["ambientCG"], f"https://ambientcg.com/view?id={aid}"
    else:
        return {"status": "failed", "errors": [f"unknown source {source}"]}
    manifest = {"source": source, "id": aid, "name": name, "type": kind, "licence": "CC0", "authors": authors,
                "page": page, "res": r, "files": {k: os.path.relpath(v, dest) for k, v in files.items()},
                "downloaded": time.strftime("%Y-%m-%d")}
    atomic_write(os.path.join(dest, "asset.json"), json.dumps(manifest, indent=1))
    if licence_log:
        new = not os.path.exists(licence_log)
        os.makedirs(os.path.dirname(os.path.abspath(licence_log)), exist_ok=True)
        with open(licence_log, "a", encoding="utf-8") as f:
            if new:
                f.write("# Asset licences\n\n| Asset | Source | Licence | Author | Link | Date |\n| --- | --- | --- | --- | --- | --- |\n")
            f.write(f"| {name} ({aid}, {r}) | {source} | CC0 | {', '.join(authors)} | {page} | {manifest['downloaded']} |\n")
    return {"status": "ok", "manifest": os.path.join(dest, "asset.json"), "files": len(files),
            "mb": round(total / 2 ** 20, 1), "res": r}
