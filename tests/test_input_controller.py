import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from process.input_controller import InputController


class TestInputController(unittest.TestCase):
    def test_clamp_drag_keeps_endpoints_inside(self):
        # Panning right by 300; start must be < 1000 so start+300 <= 1280-10.
        start = InputController._clamp_drag(500, 300, 10, 1270)
        self.assertGreaterEqual(start, 10)
        self.assertLessEqual(start + 300, 1270)

    def test_clamp_drag_longer_than_area_uses_edge(self):
        # Safe width is 1260, delta is 2000 to the right.
        start = InputController._clamp_drag(500, 2000, 10, 1270)
        self.assertEqual(start, 10)

    def test_select_color_by_key_rejects_invalid(self):
        ctrl = InputController((0, 0, 100, 100))
        with self.assertRaises(ValueError):
            ctrl.select_color_by_key(0)
        with self.assertRaises(ValueError):
            ctrl.select_color_by_key('red')


if __name__ == '__main__':
    unittest.main()
