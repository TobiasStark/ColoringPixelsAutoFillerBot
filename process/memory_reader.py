"""Low-level memory reading for the game process."""
import ctypes
import struct
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

try:
    import pymem
    from pymem.ressources.structure import MEMORY_BASIC_INFORMATION
except ImportError:
    pymem = None
    MEMORY_BASIC_INFORMATION = None


class MemoryReader:
    # Size of a single read when scanning memory. Exposed as a class attribute so
    # tests can shrink it and exercise the chunk-boundary handling.
    CHUNK_SIZE = 4 * 1024 * 1024

    def __init__(self, pid: int = None, process_name: str = None):
        if pymem is None:
            raise RuntimeError("pymem is not installed")
        # Tolerate MemoryReader("ColoringPixels.exe"); several scripts call it that way.
        if isinstance(pid, str):
            pid, process_name = None, pid
        if pid is None:
            self.pm = pymem.Pymem(process_name or config.PROCESS_EXE)
        else:
            # Pymem's constructor only accepts a process *name*, so an explicit
            # pid has to be opened separately.
            self.pm = pymem.Pymem()
            self.pm.open_process_from_id(int(pid))
        self.pid = self.pm.process_id

    def read_bytes(self, address: int, size: int) -> bytes:
        return self.pm.read_bytes(address, size)

    def read_int(self, address: int) -> int:
        return int.from_bytes(self.pm.read_bytes(address, 4), "little", signed=True)

    def read_uint(self, address: int) -> int:
        return int.from_bytes(self.pm.read_bytes(address, 4), "little", signed=False)

    def read_ptr(self, address: int) -> int:
        return self.read_uint(address)

    def read_float(self, address: int) -> float:
        return struct.unpack("<f", self.pm.read_bytes(address, 4))[0]

    def read_string(self, address: int, max_len: int = 256) -> str:
        """Read a Mono string at address (UTF-16LE, length prefix at +8)."""
        if address == 0:
            return ""
        length = self.read_int(address + 8)
        if length <= 0 or length > max_len:
            return ""
        data = self.pm.read_bytes(address + 12, length * 2)
        return data.decode("utf-16-le", errors="ignore")

    # Page protection constants worth scanning. Managed heap objects always live
    # in writable pages, so restricting to those makes scans several times faster.
    WRITABLE_PROTECT = 0x04 | 0x40 | 0x08 | 0x80  # RW, ERW, WC, WC-execute
    READABLE_PROTECT = WRITABLE_PROTECT | 0x02 | 0x20

    def iterate_regions(self, writable_only: bool = True):
        """Yield committed memory regions. By default only writable ones."""
        h = self.pm.process_handle
        base = 0
        mbi = MEMORY_BASIC_INFORMATION()
        mbi_size = ctypes.sizeof(mbi)
        mask = self.WRITABLE_PROTECT if writable_only else self.READABLE_PROTECT
        # Explicit argtypes: the size parameter is SIZE_T, which ctypes would
        # otherwise pass as a 32-bit int on 64-bit Python.
        virtual_query = ctypes.windll.kernel32.VirtualQueryEx
        virtual_query.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.c_size_t]
        virtual_query.restype = ctypes.c_size_t
        while virtual_query(h, ctypes.c_void_p(base), ctypes.byref(mbi), mbi_size):
            if mbi.State == 0x1000:  # MEM_COMMIT
                # PAGE_GUARD / PAGE_NOACCESS regions must never be touched.
                if not (mbi.Protect & 0x100 or mbi.Protect & 0x01) and (mbi.Protect & mask):
                    yield mbi.BaseAddress, mbi.RegionSize
            if mbi.RegionSize == 0:
                break
            base = mbi.BaseAddress + mbi.RegionSize

    def scan_pattern(self, pattern: bytes, writable_only: bool = True, limit: int = 0,
                     max_region_size: int = 64 * 1024 * 1024) -> list:
        """Byte scan over committed memory.

        Args:
            writable_only: only scan writable pages (managed heap).
            limit: stop after this many hits (0 = no limit).
            max_region_size: skip regions larger than this (usually graphics buffers).
        """
        results = []
        plen = len(pattern)
        chunk_size = self.CHUNK_SIZE
        for base, size in self.iterate_regions(writable_only=writable_only):
            if max_region_size and size > max_region_size:
                continue
            offset = 0
            while offset < size:
                read_size = min(chunk_size, size - offset)
                # overlap so patterns spanning a chunk boundary are still found
                if offset + read_size < size:
                    read_size = min(read_size + plen - 1, size - offset)
                try:
                    chunk = self.read_bytes(base + offset, read_size)
                except Exception:
                    offset += chunk_size
                    continue
                # A match that starts inside the overlap is reported by the next
                # chunk as well, so only accept starts before the overlap.
                stop = read_size if offset + read_size >= size else chunk_size
                start = 0
                while True:
                    idx = chunk.find(pattern, start)
                    if idx == -1 or idx >= stop:
                        break
                    results.append(base + offset + idx)
                    if limit and len(results) >= limit:
                        return results
                    start = idx + 1
                offset += chunk_size
        return results

    def scan_int_pattern(self, ints: list, **kwargs) -> list:
        """Scan for sequence of int32 values."""
        pattern = b"".join(i.to_bytes(4, "little", signed=True) for i in ints)
        return self.scan_pattern(pattern, **kwargs)

    def scan_patterns(self, patterns: list, writable_only: bool = True,
                      max_region_size: int = 64 * 1024 * 1024) -> dict:
        """Search for several byte patterns in a single pass over memory.

        Returns a dict mapping the pattern's position in `patterns` to the list of
        addresses where it was found.
        """
        results = {i: [] for i in range(len(patterns))}
        if not patterns:
            return results
        overlap = max(len(p) for p in patterns) - 1
        chunk_size = self.CHUNK_SIZE
        for base, size in self.iterate_regions(writable_only=writable_only):
            if max_region_size and size > max_region_size:
                continue
            offset = 0
            while offset < size:
                read_size = min(chunk_size + overlap, size - offset)
                try:
                    chunk = self.read_bytes(base + offset, read_size)
                except Exception:
                    offset += chunk_size
                    continue
                # Patterns shorter than `overlap` can start inside the overlap
                # region, where the next chunk would report them a second time.
                stop = read_size if offset + read_size >= size else chunk_size
                for i, pattern in enumerate(patterns):
                    start = 0
                    while True:
                        idx = chunk.find(pattern, start)
                        if idx == -1 or idx >= stop:
                            break
                        results[i].append(base + offset + idx)
                        start = idx + 1
                offset += chunk_size
        return results

    def scan_int_patterns(self, int_lists: list, **kwargs) -> dict:
        """Multi-pattern variant of scan_int_pattern."""
        patterns = [b"".join(v.to_bytes(4, "little", signed=True) for v in ints)
                    for ints in int_lists]
        return self.scan_patterns(patterns, **kwargs)


if __name__ == "__main__":
    # basic test
    import psutil
    pids = [p.pid for p in psutil.process_iter(["name"]) if p.info["name"] == config.PROCESS_EXE]
    print("pids", pids)
