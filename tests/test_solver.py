import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from process.solver import densest_cell


class TestSolver(unittest.TestCase):
    def test_densest_cell_prefers_cluster(self):
        remaining = {
            (0, 0), (1, 0), (2, 0),
            (0, 1), (1, 1), (2, 1),
            (100, 100),
        }
        # Viewport is 3x2 cells, current centre at (0, 0).
        result = densest_cell(remaining, 3, 2, 0, 0)
        # Densest cell should be inside the cluster.
        self.assertIn(result, remaining)
        self.assertNotEqual(result, (100, 100))

    def test_densest_cell_tie_breaks_to_centre(self):
        # Two equal clusters; the one closer to the current centre wins.
        cluster1 = {(0, 0), (1, 0), (0, 1), (1, 1)}
        cluster2 = {(20, 0), (21, 0), (20, 1), (21, 1)}
        remaining = cluster1 | cluster2
        result = densest_cell(remaining, 3, 3, 0, 0)
        self.assertIn(result, cluster1)

    def test_densest_cell_empty(self):
        self.assertIsNone(densest_cell(set(), 3, 3, 0, 0))


if __name__ == '__main__':
    unittest.main()
