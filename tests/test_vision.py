import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from process.vision import Vision


class TestVision(unittest.TestCase):
    def _make_vision(self):
        # Window rect large enough to contain the synthetic grid.
        return Vision((0, 0, 3000, 2000))

    def test_estimate_spacing_regular_grid(self):
        vis = self._make_vision()
        cells = []
        for y in range(5):
            for x in range(5):
                cells.append((100 + x * 54, 100 + y * 54, 50, 50))
        dx, dy = vis._estimate_spacing(cells)
        self.assertEqual(dx, 54)
        self.assertEqual(dy, 54)

    def test_estimate_spacing_missing_cells(self):
        vis = self._make_vision()
        cells = []
        for x in range(4):
            cells.append((100 + x * 54, 100, 50, 50))
        for x in range(4):
            cells.append((100 + x * 54, 208, 50, 50))
        dx, dy = vis._estimate_spacing(cells)
        self.assertEqual(dx, 54)
        self.assertEqual(dy, 108)

    def test_filter_by_expected_size(self):
        vis = self._make_vision()
        cells = [
            (50, 50, 54, 54),  # good
            (150, 50, 200, 50),  # merged / too wide
            (250, 50, 54, 200),  # too tall
        ]
        filtered = vis._filter_by_expected_size(cells, 54, 54)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0], (50, 50, 54, 54))

    def test_build_grid_mapping_calibrates_origin(self):
        """Synthetic full-grid calibration: every second cell uncoloured."""
        vis = self._make_vision()
        # Force the detector to report a known set of cells.
        # Place the grid well inside the margins so the auto-prior sees the whole grid.
        ox, oy = 400, 400
        dx, dy = 50, 50
        expected_cells = []
        for gy in range(4):
            for gx in range(4):
                if (gx + gy) % 2 == 0:
                    expected_cells.append((ox + gx * dx, oy + gy * dy, 46, 46))

        def fake_detect():
            return list(expected_cells)

        vis.detect_uncolored_cells = fake_detect

        x_max, y_max = 4, 4
        saved = [[0] * x_max for _ in range(y_max)]
        main = [[0] * x_max for _ in range(y_max)]
        for y in range(y_max):
            for x in range(x_max):
                if (x + y) % 2 == 0:
                    saved[y][x] = -1
                    main[y][x] = 1
        mapping, rdx, rdy = vis.build_grid_mapping(saved, main)
        self.assertEqual(rdx, dx)
        self.assertEqual(rdy, dy)
        # The top-left uncoloured cell (0,0) should map to (ox, oy).
        self.assertEqual(mapping[(0, 0)], (ox, oy))
        # (2,0) should be exactly two cells right.
        self.assertEqual(mapping[(2, 0)], (ox + 2 * dx, oy))

    def test_origin_score_counts_correct_cells(self):
        vis = self._make_vision()
        # 2x2 mask: logical (x=0, y=1) is uncolored.
        saved = [[0, 0], [-1, 0]]
        main = [[0, 0], [1, 0]]
        mask = (np.asarray(main) != 0) & (np.asarray(saved) != np.asarray(main))
        # Let's test _origin_score with direct inputs.
        # cell_pts is one cell that is one dy below the origin: it maps to logical (0,1).
        cell_pts = np.array([[10, 60]], dtype=float)
        score = Vision._origin_score(
            cell_pts, mask, 10, 10, 50, 50,
            10, 10, 50, 0.0)
        # (10,60) -> gx=0, gy=1 -> mask[1, 0] is True
        self.assertEqual(score, 1.0)

        # Offset by one dy so the same cell maps to (0,0), which is not uncolored.
        score = Vision._origin_score(
            cell_pts, mask, 10, 60, 50, 50,
            10, 60, 50, 0.0)
        # (10,60) -> gx=0, gy=0 -> mask[0,0] is False
        self.assertEqual(score, 0.0)


if __name__ == '__main__':
    unittest.main()
