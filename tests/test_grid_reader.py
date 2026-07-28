import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from process.grid_reader import GridReader


class FakeReader:
    """MemoryReader stand-in for grid-reading tests."""

    def __init__(self, data: dict):
        self.data = data

    def read_int(self, address):
        return self.data[address]

    def read_ptr(self, address):
        return self.data[address]

    def read_bytes(self, address, size):
        return self.data[(address, size)]


class TestGridReader(unittest.TestCase):
    def test_to_logical_small_grid(self):
        reader = FakeReader({})
        gr = GridReader(reader)
        # Memory order: column-major, bottom-to-top within each column.
        # For a 2x3 grid, columns are x=0 then x=1, each storing y=2,1,0.
        flat = [10, 11, 12,  # x=0: y=2,1,0
                20, 21, 22]  # x=1
        # Expected top-to-bottom rows:
        # row 0 (y=0): [12, 22]
        # row 1 (y=1): [11, 21]
        # row 2 (y=2): [10, 20]
        logical = gr.to_logical(flat, 2, 3)
        self.assertEqual(logical, [[12, 22], [11, 21], [10, 20]])

    def test_to_logical_numpy_input(self):
        import numpy as np
        reader = FakeReader({})
        gr = GridReader(reader)
        flat = np.array([1, 2, 3, 4, 5, 6], dtype=np.int32)
        logical = gr.to_logical(flat, 3, 2)
        # Memory order is y=0 (bottom) first per column, then y=1 (top).
        # arr[x][0] = bottom, arr[x][1] = top. After transposing and flipping
        # top-to-bottom, row 0 is top (y=1) and row 1 is bottom (y=0).
        self.assertEqual(logical, [[2, 4, 6], [1, 3, 5]])

    def test_read_int_array_parses_bytes(self):
        import numpy as np
        reader = FakeReader({
            100 + 12: 6,  # max_len
            (100 + 16, 6 * 4): np.array([1, 2, 3, 4, 5, 6], dtype='<i4').tobytes(),
        })
        gr = GridReader(reader)
        arr = gr.read_int_array(100, 3, 2)
        self.assertListEqual(arr.tolist(), [1, 2, 3, 4, 5, 6])

    def test_dims_plausible(self):
        from process.grid_reader import MAX_GRID_DIM
        self.assertTrue(GridReader._dims_plausible(5, 10))
        self.assertTrue(GridReader._dims_plausible(MAX_GRID_DIM, MAX_GRID_DIM))
        self.assertFalse(GridReader._dims_plausible(0, 10))
        self.assertFalse(GridReader._dims_plausible(10, -1))
        self.assertFalse(GridReader._dims_plausible(MAX_GRID_DIM + 1, 5))


if __name__ == '__main__':
    unittest.main()
