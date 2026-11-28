"""Low-overhead machine readings for the Studio, using only unprivileged methods.

macOS (Apple Silicon):
  CPU          host_statistics(HOST_CPU_LOAD_INFO) through ctypes, difference between samples
  memory       vm_stat pages + sysctl hw.memsize. Unified memory: one pool shared by CPU and GPU
  pressure     sysctl kern.memorystatus_vm_pressure_level (1 normal, 2 warning, 4 critical)
  swap         sysctl vm.swapusage
  GPU          ioreg IOAccelerator "Device Utilization %" and "In use system memory" (part of unified memory)
  thermal      NSProcessInfo.thermalState (nominal, fair, serious, critical). Temperatures need
               privileged sensors, so they are reported as unavailable.
Linux (the Cowork VM): /proc/stat, /proc/meminfo, /proc/pressure/memory. No GPU or thermal readings.
Everything that cannot be read is returned as {"available": False, "why": ...}, never a guess.
"""
import os
import re
import shutil
import subprocess
import sys
import time

try:
    import resource
except ImportError:  # Windows
    resource = None

WORKLOAD_RE = re.compile(r"(?i)(blender|ffmpeg|ffprobe|vfx\.py|comp_worker|depth_mac|colmap)")
THERMAL = {0: "nominal", 1: "fair", 2: "serious", 3: "critical"}
PRESSURE = {1: "normal", 2: "warning", 4: "critical"}


def _run(cmd, timeout=3):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def na(why):
    return {"available": False, "why": why}


# ---------- CPU ticks ----------
def _mac_ticks():
    try:
        import ctypes
        libc = ctypes.CDLL("/usr/lib/libSystem.dylib")
        libc.mach_host_self.restype = ctypes.c_uint
        info = (ctypes.c_uint32 * 4)()
        cnt = ctypes.c_uint32(4)
        if libc.host_statistics(libc.mach_host_self(), 3, ctypes.byref(info), ctypes.byref(cnt)) != 0:
            return None
        user, system, idle, nice = list(info)
        return user + system + nice, user + system + idle + nice
    except Exception:
        return None


def _linux_ticks():
    try:
        with open("/proc/stat") as f:
            v = [int(x) for x in f.readline().split()[1:]]
        idle = v[3] + (v[4] if len(v) > 4 else 0)
        return sum(v) - idle, sum(v)
    except (OSError, ValueError, IndexError):
        return None


# ---------- macOS ----------
def _sysctl(name):
    out = _run(["sysctl", "-n", name])
    return out.strip() if out else None


def _mac_memory():
    total = _sysctl("hw.memsize")
    vm = _run(["vm_stat"])
    if not total or not vm:
        return na("vm_stat or sysctl unavailable")
    page = int(re.search(r"page size of (\d+)", vm).group(1)) if "page size of" in vm else 16384
    pages = {k.strip().strip('"'): int(v.strip().rstrip(".")) for k, v in re.findall(r"^([^:]+):\s+(\d+)\.?$", vm, re.M)}
    app = pages.get("Anonymous pages", 0) - pages.get("Pages purgeable", 0)
    used = (app + pages.get("Pages wired down", 0) + pages.get("Pages occupied by compressor", 0)) * page
    total = int(total)
    return {"available": True, "total_gb": round(total / 2**30, 1), "used_gb": round(used / 2**30, 1),
            "used_pct": round(100.0 * used / total, 1), "unified": True,
            "method": "app + wired + compressed pages (Activity Monitor's Memory Used)"}


def _mac_pressure():
    v = _sysctl("kern.memorystatus_vm_pressure_level")
    if v is None or not v.isdigit():
        return na("pressure level not readable")
    return {"available": True, "level": PRESSURE.get(int(v), f"level {v}")}


def _mac_swap():
    v = _sysctl("vm.swapusage")
    m = re.search(r"total = ([\d.]+)M\s+used = ([\d.]+)M", v or "")
    if not m:
        return na("vm.swapusage not readable")
    total, used = float(m.group(1)) / 1024, float(m.group(2)) / 1024
    return {"available": True, "total_gb": round(total, 2), "used_gb": round(used, 2),
            "used_pct": round(100 * used / total, 1) if total else 0.0}


def _mac_gpu():
    out = _run(["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"])
    if not out:
        return na("IOAccelerator not readable")
    util = re.search(r'"Device Utilization %"=(\d+)', out)
    mem = re.search(r'"In use system memory"=(\d+)', out)
    name = re.search(r'"model"\s*=\s*"([^"]+)"', out) or re.search(r'"IOGLBundleName"\s*=\s*"([^"]+)"', out)
    if not util:
        return na("this GPU does not report utilisation")
    return {"available": True, "busy_pct": int(util.group(1)), "name": name.group(1) if name else None,
            "unified_memory_in_use_gb": round(int(mem.group(1)) / 2**30, 2) if mem else None,
            "method": "IOKit Device Utilization %"}


def _mac_thermal():
    try:
        import ctypes
        objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        pi = send(objc.objc_getClass(b"NSProcessInfo"), objc.sel_registerName(b"processInfo"))
        send.restype = ctypes.c_long
        state = send(pi, objc.sel_registerName(b"thermalState"))
        send.restype = ctypes.c_void_p
        return {"available": True, "state": THERMAL.get(state, f"state {state}"),
                "temperature": "not available without elevated access", "method": "NSProcessInfo.thermalState"}
    except Exception as e:
        return na(f"thermal state not readable ({type(e).__name__})")


# ---------- Linux ----------
def _linux_memory():
    try:
        with open("/proc/meminfo") as f:
            m = {k: int(v.split()[0]) for k, v in (l.split(":", 1) for l in f)}
        total, avail = m["MemTotal"], m.get("MemAvailable", m["MemFree"])
        mem = {"available": True, "total_gb": round(total / 2**20, 1), "used_gb": round((total - avail) / 2**20, 1),
               "used_pct": round(100.0 * (total - avail) / total, 1), "unified": False, "method": "/proc/meminfo"}
        st, sf = m.get("SwapTotal", 0), m.get("SwapFree", 0)
        swap = {"available": True, "total_gb": round(st / 2**20, 2), "used_gb": round((st - sf) / 2**20, 2),
                "used_pct": round(100 * (st - sf) / st, 1) if st else 0.0}
        return mem, swap
    except (OSError, ValueError, KeyError):
        return na("/proc/meminfo not readable"), na("/proc/meminfo not readable")


def _linux_pressure():
    try:
        with open("/proc/pressure/memory") as f:
            some = float(re.search(r"some avg10=([\d.]+)", f.read()).group(1))
        return {"available": True, "level": "critical" if some > 40 else "warning" if some > 10 else "normal",
                "stall_pct_10s": some}
    except (OSError, AttributeError, ValueError):
        return na("no pressure information on this kernel")


def _workloads(own_pid):
    out = _run(["ps", "-A", "-o", "pid=,pcpu=,rss=,args="])
    if out is None:
        return na("ps not available"), None
    found, own = [], None
    for line in out.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        pid, cpu, rss, args = parts
        try:
            pid, cpu, rss = int(pid), float(cpu), int(rss)
        except ValueError:
            continue
        if pid == own_pid:
            own = {"rss_mb": round(rss / 1024, 1)}
            continue
        if WORKLOAD_RE.search(args) and not args.startswith("ps "):
            name = os.path.basename(args.split()[0])
            role = "Blender" if "blender" in args.lower() else "ffmpeg" if "ffmpeg" in args.lower() else \
                "VFX engine" if "vfx.py" in args else "processing"
            found.append({"pid": pid, "name": name[:40], "role": role, "cpu_pct_of_one_core": cpu, "rss_mb": round(rss / 1024)})
    found.sort(key=lambda w: -w["cpu_pct_of_one_core"])
    return {"available": True, "processes": found[:8], "count": len(found)}, own


class Sampler:
    """Keeps the last reading. sample() is cheap but runs a few small commands (vm_stat, sysctl,
    ioreg, ps), so callers sample every few seconds at most. Overhead is measured, including the
    CPU used by those commands."""

    def __init__(self, disk_path="/"):
        self.disk_path = disk_path
        self.mac = sys.platform == "darwin"
        self.prev_ticks = None
        self.prev_own = None
        self.last = None
        self.cost = []
        t = self._ticks()  # baseline, so the first sample already has a CPU figure
        self.prev_ticks = (time.time(), t) if t else None

    def _ticks(self):
        return _mac_ticks() if self.mac else _linux_ticks() if sys.platform.startswith("linux") else None

    def _own_cpu(self):
        """CPU seconds of this process plus the commands it ran (vm_stat, ioreg, ps)."""
        if resource is None:
            return time.process_time()
        r, c = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        return r.ru_utime + r.ru_stime + c.ru_utime + c.ru_stime

    def sample(self):
        from .events import machine_kind
        t0, c0 = time.time(), self._own_cpu()
        now = time.time()
        ticks = self._ticks()
        cpu = na("CPU counters not readable")
        if ticks and self.prev_ticks:
            busy, total = ticks[0] - self.prev_ticks[1][0], ticks[1] - self.prev_ticks[1][1]
            if total > 0:
                cpu = {"available": True, "busy_pct": round(100.0 * busy / total, 1), "cores": os.cpu_count(),
                       "over_s": round(now - self.prev_ticks[0], 1)}
                self.prev_ticks = (now, ticks)
            else:  # too soon after the last reading for the counters to move
                cpu = (self.last or {}).get("cpu") or na("measuring, ready in a second")
        elif ticks:
            cpu = na("measuring, ready in a second")
            self.prev_ticks = (now, ticks)
        if self.mac:
            mem, pressure, swap, gpu, thermal = _mac_memory(), _mac_pressure(), _mac_swap(), _mac_gpu(), _mac_thermal()
        elif sys.platform.startswith("linux"):
            (mem, swap), pressure = _linux_memory(), _linux_pressure()
            gpu, thermal = na("no GPU readings on this machine"), na("no thermal readings on this machine")
        else:
            mem = swap = pressure = gpu = thermal = na(f"not supported on {sys.platform}")
        try:
            du = shutil.disk_usage(self.disk_path)
            disk = {"available": True, "path": self.disk_path, "free_gb": round(du.free / 2**30, 1),
                    "total_gb": round(du.total / 2**30, 1), "free_pct": round(100.0 * du.free / du.total, 1)}
        except OSError as e:
            disk = na(f"cannot read free space ({e.strerror})")
        work, own_mem = _workloads(os.getpid())
        own_cpu_now = self._own_cpu()
        studio = {"available": True, "rss_mb": own_mem["rss_mb"] if own_mem else None}
        if self.prev_own:
            studio["cpu_pct"] = round(100.0 * (own_cpu_now - self.prev_own[1]) / max(1e-6, now - self.prev_own[0]), 2)
        self.prev_own = (now, own_cpu_now)
        cost_s = self._own_cpu() - c0
        self.cost.append((now, cost_s, time.time() - t0))
        self.cost = self.cost[-60:]
        self.last = {"t": round(now, 1), "machine": machine_kind(), "cpu": cpu, "gpu": gpu, "memory": mem,
                     "pressure": pressure, "swap": swap, "disk": disk, "thermal": thermal, "workloads": work,
                     "studio": studio, "sample_cpu_s": round(cost_s, 4), "sample_wall_s": round(time.time() - t0, 3)}
        return self.last
