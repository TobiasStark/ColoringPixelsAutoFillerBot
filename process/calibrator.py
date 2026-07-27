"""Calibrate screen-to-logical mapping by clicking a grid and reading memory."""
import time
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from process.memory_reader import MemoryReader
from process.grid_reader import GridReader
from process.input_controller import InputController
from process.window_manager import WindowManager


class Calibrator:
    def __init__(self, x_step=108, y_step=108):
        self.reader = MemoryReader(process_name="ColoringPixels.exe")
        self.grid = GridReader(self.reader)
        self.window = WindowManager()
        self.window.update_rect()
        self.controller = InputController(self.window.client_rect())
        self.x_step = x_step
        self.y_step = y_step
        # Fullscreen 1920x1080 palette positions will be updated before use
        self.palette = {1: (204, 970), 2: (342, 970), 3: (458, 970)}
        self.controller.set_palette_positions(self.palette)

    def collect(self):
        """Return dict logical->screen (client center) by clicking a grid across colors.

        Hits all cells that are not yet correctly coloured, then returns the
        median screen point for each logical cell that changed.
        """
        self.window.focus()
        time.sleep(0.3)
        info = self.grid.read_grids()
        x_max, y_max = info["x_max"], info["y_max"]
        hits = {}
        left, top, w, h = self.window.client_rect()
        # Only scan the grid area to avoid UI elements
        pts = [(x, y) for y in range(100, h - 160, self.y_step)
               for x in range(520, w - 300, self.x_step)]
        for color in (2, 1, 3):
            self.controller.select_color(color)
            time.sleep(0.2)
            for sx, sy in pts:
                before = self.grid.read_grids()["saved"]
                self.controller.click(sx, sy, duration=0.03)
                time.sleep(0.08)
                after = self.grid.read_grids()["saved"]
                for ly in range(y_max):
                    for lx in range(x_max):
                        if before[ly][lx] != after[ly][lx]:
                            hits.setdefault((lx, ly), []).append((sx, sy))
        mapping = {cell: (np.median([p[0] for p in pts]), np.median([p[1] for p in pts]))
                   for cell, pts in hits.items() if pts}
        return mapping

    def fit_homography(self, mapping):
        """Fit a projective homography logical->screen from mapping dict."""
        pts = np.array([(lx, ly, sx, sy) for (lx, ly), (sx, sy) in mapping.items()], dtype=float)
        if len(pts) < 4:
            return None
        A = []
        b = []
        for lx, ly, sx, sy in pts:
            A.append([lx, ly, 1, 0, 0, 0, -lx * sx, -ly * sx])
            A.append([0, 0, 0, lx, ly, 1, -lx * sy, -ly * sy])
            b.append(sx)
            b.append(sy)
        A = np.array(A)
        b = np.array(b)
        h = np.linalg.lstsq(A, b, rcond=None)[0]
        return h

    def predict(self, h, lx, ly):
        denom = h[6] * lx + h[7] * ly + 1
        sx = (h[0] * lx + h[1] * ly + h[2]) / denom
        sy = (h[3] * lx + h[4] * ly + h[5]) / denom
        return sx, sy

    def save_debug(self, mapping, path="data/calibration.json"):
        import json
        out = {f"{x},{y}": (sx, sy) for (x, y), (sx, sy) in mapping.items()}
        with open(path, "w") as f:
            json.dump(out, f)


if __name__ == "__main__":
    cal = Calibrator()
    m = cal.collect()
    print("mapped", len(m), "cells")
    h = cal.fit_homography(m)
    print("homography", h)
    cal.save_debug(m)
