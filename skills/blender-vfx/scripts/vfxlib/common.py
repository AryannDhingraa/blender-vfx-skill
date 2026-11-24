"""Small helpers shared by every tool: compact JSON output, frame ranges,
file fingerprints and a cross-platform file lock."""
import hashlib
import json
import os
import re
import sys
import time

HASH_FULL_LIMIT = 8 * 1024 * 1024  # files up to 8 MB are hashed whole


def out(obj, code=0):
    print(json.dumps(obj, separators=(",", ":"), default=str))
    return code


def compress_ranges(nums):
    """[1,2,3,7,9,10] -> '1-3,7,9-10'"""
    nums = sorted(set(int(n) for n in nums))
    if not nums:
        return ""
    parts, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(f"{start}-{prev}" if prev != start else str(start))
        start = prev = n
    parts.append(f"{start}-{prev}" if prev != start else str(start))
    return ",".join(parts)


def parse_ranges(text):
    """'1-3,7' or '1..3,7' -> [1,2,3,7]"""
    nums = []
    for part in str(text).replace("..", "-").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(-?\d+)\s*-\s*(-?\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            nums.extend(range(min(a, b), max(a, b) + 1))
        else:
            nums.append(int(part))
    return sorted(set(nums))


def blender_frames(nums):
    """Frame list in Blender's -f syntax: '1..3,7'"""
    return compress_ranges(nums).replace("-", "..")


def _hash_file(path, size):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if size <= HASH_FULL_LIMIT:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        else:  # head + tail + size: cheap, catches rewrites and truncation
            h.update(f.read(1 << 20))
            f.seek(max(0, size - (1 << 20)))
            h.update(f.read(1 << 20))
            h.update(str(size).encode())
    return h.hexdigest()[:16]


def fingerprint(path):
    """Content fingerprint for a file or a folder (e.g. a frame sequence).
    Folders: every file's relative name, size and mtime, so adding, removing
    or re-rendering any frame changes it. Returns None if the path is gone."""
    if os.path.isfile(path):
        st = os.stat(path)
        return {"kind": "file", "size": st.st_size, "hash": _hash_file(path, st.st_size)}
    if os.path.isdir(path):
        h, count, total = hashlib.sha256(), 0, 0
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                if name.startswith("."):
                    continue
                p = os.path.join(root, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                h.update(f"{os.path.relpath(p, path)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
                count += 1
                total += st.st_size
        return {"kind": "dir", "files": count, "size": total, "hash": h.hexdigest()[:16]}
    return None


class LockTimeout(Exception):
    pass


class FileLock:
    """Exclusive lock on <path>. Uses OS locks (released automatically if the
    process dies), so a crash can never leave a stale lock behind."""

    def __init__(self, path, timeout=30.0):
        self.path, self.timeout, self.fh = path, timeout, None

    def __enter__(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.fh = open(self.path, "a+")
        deadline = time.time() + self.timeout
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self.fh.seek(0)
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    self.fh.close()
                    raise LockTimeout(f"{self.path} is locked by another process")
                time.sleep(0.05)
        try:
            self.fh.seek(0)
            self.fh.truncate()
            self.fh.write(f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
            self.fh.flush()
        except OSError:
            pass
        return self

    def __exit__(self, *exc):
        try:
            if sys.platform == "win32":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()


def atomic_write(path, data):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def pid_alive(pid):
    if not pid:
        return False
    if sys.platform == "win32":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
