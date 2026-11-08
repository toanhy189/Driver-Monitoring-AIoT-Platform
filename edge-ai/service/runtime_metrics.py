"""Process measurements, independent of network and camera hardware."""

from collections import defaultdict, deque
import ctypes
import json
import os
from pathlib import Path
import sys
import time


def rss_bytes():
    if sys.platform == "win32":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
        return None
    try:
        if Path("/proc/self/statm").exists():
            return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError):
        pass
    return None


class RuntimeMetrics:
    def __init__(self, output=None, clock=time.perf_counter):
        self.clock, self.output = clock, Path(output) if output else None
        self.started = self.clock()
        self.cpu_started = time.process_time()
        self.values = defaultdict(lambda: deque(maxlen=600))
        self.frames = deque(maxlen=600)

    def observe(self, stage, milliseconds):
        if milliseconds is not None:
            self.values[stage].append(float(milliseconds))

    def frame(self):
        self.frames.append(self.clock())

    def snapshot(self):
        def stats(values):
            ordered = sorted(values)
            return {"count": len(ordered), "p50_ms": ordered[(len(ordered)-1)//2],
                    "p95_ms": ordered[min(len(ordered)-1, int(len(ordered)*0.95))]}
        wall = self.clock() - self.started
        return {"fps": ((len(self.frames)-1)/(self.frames[-1]-self.frames[0])
                         if len(self.frames) > 1 and self.frames[-1] > self.frames[0] else None),
                "cpu_process_percent": 100*(time.process_time()-self.cpu_started)/wall if wall > 0 else None,
                "rss_bytes": rss_bytes(), "stages": {key: stats(value) for key, value in self.values.items() if value}}

    def write(self, **identity):
        result = {**identity, **self.snapshot()}
        if self.output:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            # Rotate measurements, never camera recordings.
            if self.output.exists() and self.output.stat().st_size > 5*1024*1024:
                self.output.replace(self.output.with_suffix(".previous.jsonl"))
            with self.output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(result, allow_nan=False)+"\n")
        return result
