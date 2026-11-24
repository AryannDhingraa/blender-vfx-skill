"""Detect the machine and turn it into budgets: texture size, polycount, tier."""
import os
import platform
import re
import shutil
import subprocess
import sys


def _run(cmd, timeout=15):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def ram_gb():
    try:
        if sys.platform == "darwin":
            return round(int(_run(["sysctl", "-n", "hw.memsize"]).strip()) / 2 ** 30, 1)
        if sys.platform == "win32":
            import ctypes

            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                            ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            m = M()
            m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 2 ** 30, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except (ValueError, OSError, AttributeError):
        return None


def gpus():
    out = []
    if shutil.which("nvidia-smi"):
        for line in _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]).splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 2 and parts[1].isdigit():
                out.append({"name": parts[0], "vram_gb": round(int(parts[1]) / 1024, 1), "vendor": "nvidia"})
    if sys.platform == "darwin" and platform.machine() == "arm64":
        chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip() or "Apple Silicon"
        out.append({"name": chip, "vram_gb": None, "vendor": "apple", "unified": True})
    return out


def detect():
    g = gpus()
    ram = ram_gb()
    info = {"os": platform.system(), "os_version": platform.release(), "cpu": platform.processor() or platform.machine(),
            "cores": os.cpu_count(), "ram_gb": ram, "gpus": g}
    info.update(budget_for(g, ram))
    return info


def budget_for(gpu_list=None, ram=None, vram=None, unified=None):
    """Memory the renderer can realistically use, and what that allows."""
    gpu_list = gpu_list or []
    if vram is None and gpu_list:
        nv = [x for x in gpu_list if x.get("vendor") == "nvidia" and x.get("vram_gb")]
        if nv:
            vram = max(x["vram_gb"] for x in nv)
        elif any(x.get("unified") for x in gpu_list):
            unified = True
    if unified and ram:
        mem, tier = round(ram * 0.6, 1), "apple-silicon"
    elif vram:
        mem = vram
        name = " ".join(x["name"] for x in gpu_list)
        tier = "nvidia-rtx" if re.search(r"RTX|A\d{4}", name) else "nvidia"
    else:
        mem, tier = (round(ram * 0.5, 1) if ram else 8), "cpu"
    if mem <= 4:
        tex, poly_ok, poly_heavy = "2k", 200_000, 1_000_000
    elif mem <= 8:
        tex, poly_ok, poly_heavy = "2k", 500_000, 3_000_000
    elif mem <= 16:
        tex, poly_ok, poly_heavy = "4k", 2_000_000, 8_000_000
    else:
        tex, poly_ok, poly_heavy = "4k", 5_000_000, 20_000_000
    return {"tier": tier, "render_memory_gb": mem, "texture_res": tex, "poly_ok": poly_ok, "poly_heavy": poly_heavy}
