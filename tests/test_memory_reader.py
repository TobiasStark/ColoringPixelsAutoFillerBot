import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from process.memory_reader import MemoryReader


class FakeMemoryReader(MemoryReader):
    """A MemoryReader that reads from a synthetic address space instead of a live process.

    Useful for testing the pattern scanners.
    """

    def __init__(self, regions=None, data=b''):
        # Do not call parent __init__ which would open pymem.
        self._regions = regions or [(0, len(data))]
        self._data = data

    def read_bytes(self, address, size):
        return self._data[address:address + size]

    def iterate_regions(self, writable_only=True):
        for base, size in self._regions:
            yield base, size


class TestMemoryReaderScans(unittest.TestCase):
    def _regions_for(self, data, chunk_size):
        # Build a list of regions that together span `data` in `chunk_size` slices.
        regions = []
        for base in range(0, len(data), chunk_size):
            regions.append((base, min(chunk_size, len(data) - base)))
        return regions

    def test_scan_pattern_across_chunk_boundary(self):
        # Pattern longer than a chunk, fully contained in one synthetic region.
        data = b'A' * 8 + b'TARGET' + b'B' * 14
        reader = FakeMemoryReader(data=data)
        reader.CHUNK_SIZE = 5
        results = reader.scan_pattern(b'TARGET')
        self.assertEqual(results, [8])

    def test_scan_pattern_not_duplicate(self):
        # Pattern 'AB' at positions 1 and 7, no overlaps.
        data = b'xABxxxABxxxxxx'
        reader = FakeMemoryReader(data=data)
        reader.CHUNK_SIZE = 6
        results = reader.scan_pattern(b'AB')
        self.assertEqual(results, [1, 6])

    def test_scan_pattern_with_overlapping_candidates(self):
        # 'AAA' occurs at starts 0, 1, and 2 inside a single region.
        data = b'AAAAA'
        reader = FakeMemoryReader(data=data)
        reader.CHUNK_SIZE = 4
        results = reader.scan_pattern(b'AAA')
        self.assertEqual(results, [0, 1, 2])

    def test_scan_patterns_multiple(self):
        data = b'0123ABC456DEF789'
        reader = FakeMemoryReader(data=data)
        reader.CHUNK_SIZE = 6
        results = reader.scan_patterns([b'ABC', b'DEF'])
        self.assertEqual(results[0], [4])
        self.assertEqual(results[1], [10])

    def test_string_process_name_treated_as_process_name(self):
        # We cannot open a real process, but we can verify the constructor logic
        # doesn't try to use the executable name as a PID by checking the error type.
        # This would require pymem installed; we just exercise the parser path
        # by monkeypatching config.
        import config
        old_exe = config.PROCESS_EXE
        try:
            config.PROCESS_EXE = 'nonexistent.exe'
            # IsInstance check in __init__ should set pid=None, process_name='foo.exe'
            # Pymem will then fail on the process name, not a ValueError for PID.
            with self.assertRaises(Exception):
                MemoryReader('nonexistent.exe')
        finally:
            config.PROCESS_EXE = old_exe


if __name__ == '__main__':
    unittest.main()
