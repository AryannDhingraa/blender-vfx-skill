"""Audit a VFX project folder: clutter, duplicates, temp files, old versions.

Never deletes anything without an explicit flag, and only deletes files that
are byte-identical to a kept file (checked with SHA-256) or inside _tmp/.
Prints one compact JSON report so agents can read it cheaply.
"""
import collections
import hashlib
import os
import re
import shutil

STANDARD = {"00_brief", "01_source", "02_plates", "03_track", "04_assets", "05_blend", "06_cache",
            "07_renders", "08_comp", "09_deliver", "scripts", "logs", "_review", "_tmp", "_archive",
            ".git"}
ROOT_OK = {"README.md", ".gitignore", ".DS_Store"}
TEMP_RE = re.compile(r"(_tmp_|\.tmp$|~$|\.blend\d+$)", re.I)
SOURCE_RE = re.compile(r"^(01_source|02_plates|plates?\d*|source|footage)(/|$)", re.I)
DERIVED_RE = re.compile(r"(^|/)(_tmp|_review|_archive|comp\d*|preview|review|render\w*|08_comp)(/|$)", re.I)
VERSIONED_SCRIPT_RE = re.compile(r"(_v\d+|_final\d*|_new|_old|_copy|\(\d+\))\.(py|sh)$", re.I)


def sha(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def mb(n):
    return round(n / 1e6, 1)


def audit(root, plan=False, clear_tmp=False, delete_duplicates=False):
    root = os.path.abspath(os.path.expanduser(root))

    files = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != ".git"]
        for f in fn:
            p = os.path.join(dp, f)
            try:
                files.append((os.path.relpath(p, root).replace(os.sep, "/"), os.path.getsize(p)))
            except OSError:
                pass

    total = sum(s for _, s in files)
    root_clutter = [f for f, _ in files if "/" not in f and f not in ROOT_OK]
    top_dirs = sorted({f.split("/")[0] for f, _ in files if "/" in f})
    nonstandard = [d for d in top_dirs if d not in STANDARD]
    temp = [(f, s) for f, s in files if TEMP_RE.search(f) and not f.startswith("_tmp/")]
    versioned_scripts = [f for f, _ in files if VERSIONED_SCRIPT_RE.search(os.path.basename(f))]

    # duplicates: same size first, then hash
    by_size = collections.defaultdict(list)
    for f, s in files:
        if s > 0:
            by_size[s].append(f)
    dup_groups = []
    for s, group in by_size.items():
        if len(group) < 2:
            continue
        by_hash = collections.defaultdict(list)
        for f in group:
            by_hash[sha(os.path.join(root, f))].append(f)
        for g in by_hash.values():
            if len(g) > 1:
                # keep: no temp marker, source or plate folders first, derived folders last
                g.sort(key=lambda x: (bool(TEMP_RE.search(x)), not SOURCE_RE.search(x),
                                      bool(DERIVED_RE.search(x)), len(x), x))
                dup_groups.append({"keep": g[0], "copies": g[1:], "size": s})
    dup_bytes = sum(d["size"] * len(d["copies"]) for d in dup_groups)

    folders = collections.Counter()
    folder_bytes = collections.Counter()
    for f, s in files:
        top = f.split("/")[0] if "/" in f else "(root)"
        folders[top] += 1
        folder_bytes[top] += s

    report = {
        "root": root, "files": len(files), "total_mb": mb(total),
        "folders": {k: [folders[k], mb(folder_bytes[k])] for k in sorted(folders, key=lambda k: -folder_bytes[k])},
        "root_clutter": root_clutter[:30],
        "nonstandard_folders": nonstandard,
        "temp_or_backup": {"count": len(temp), "mb": mb(sum(s for _, s in temp)), "examples": [f for f, _ in temp[:5]]},
        "versioned_script_copies": versioned_scripts[:20],
        "duplicates": {"groups": len(dup_groups), "extra_copies": sum(len(d["copies"]) for d in dup_groups),
                       "mb_wasted": mb(dup_bytes), "examples": dup_groups[:3]},
    }

    if plan:
        plan = []
        for f in root_clutter:
            ext = os.path.splitext(f)[1].lower()
            dest = {".py": "scripts/", ".sh": "scripts/", ".json": "03_track/", ".blend": "05_blend/",
                    ".mp4": "09_deliver/", ".mov": "09_deliver/", ".txt": "logs/", ".log": "logs/",
                    ".jpg": "_review/", ".png": "_review/", ".md": "00_brief/"}.get(ext, "_archive/")
            plan.append([f, dest])
        report["suggested_moves"] = plan

    if clear_tmp:
        tmp = os.path.join(root, "_tmp")
        if os.path.isdir(tmp):
            shutil.rmtree(tmp)
            os.makedirs(tmp)
        report["cleared_tmp"] = True

    if delete_duplicates:
        removed = 0
        for d in dup_groups:
            keep_hash = sha(os.path.join(root, d["keep"]))
            for c in d["copies"]:
                p = os.path.join(root, c)
                if sha(p) == keep_hash:
                    os.remove(p)
                    removed += 1
        report["duplicates_removed"] = removed

    return report
