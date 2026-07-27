"""Solve a level by reading grid and clicking cells."""
import json
import time
import ctypes
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from process.memory_reader import MemoryReader
from process.grid_reader import GridReader
from process.input_controller import InputController
from process.window_manager import WindowManager
from process.vision import Vision


class HomographyMapper:
    def __init__(self, mapping):
        pts = np.array([(lx, ly, sx, sy) for (lx, ly), (sx, sy) in mapping.items()], dtype=float)
        if len(pts) < 4:
            raise ValueError("Need at least 4 calibration points")
        A = []
        b = []
        for lx, ly, sx, sy in pts:
            A.append([lx, ly, 1, 0, 0, 0, -lx * sx, -ly * sx])
            A.append([0, 0, 0, lx, ly, 1, -lx * sy, -ly * sy])
            b.extend([sx, sy])
        self.h = np.linalg.lstsq(np.array(A), np.array(b), rcond=None)[0]

    def to_screen(self, x, y):
        return self.to_client(x, y)

    def to_client(self, x, y):
        h = self.h
        denom = h[6] * x + h[7] * y + 1
        sx = (h[0] * x + h[1] * y + h[2]) / denom
        sy = (h[3] * x + h[4] * y + h[5]) / denom
        return sx, sy


class Solver:
    def __init__(self, mapper: HomographyMapper = None, palette_positions: dict = None,
                 book_name: str = "Book1", save_file: str = None, base: int = None):
        self.reader = MemoryReader(process_name="ColoringPixels.exe")
        self.grid = GridReader(self.reader)
        # Address of the CrossLevelStorage singleton; reused across reads because
        # the object is DontDestroyOnLoad and therefore never moves.
        self.base = base or 0
        if self.base:
            self.grid._base_cache = self.base
        self.window = WindowManager()
        self.window.update_rect()
        self.controller = InputController(self.window.client_rect())
        self.vision = Vision(self.window.client_rect())
        self.mapper = mapper
        self.palette_positions = palette_positions
        self.max_retries = 2
        self.book_name = book_name
        self.save_file = save_file

    def _read_grids(self):
        info = self.grid.read_grids(base=self.base or None, book_name=self.book_name,
                                    save_file=self.save_file)
        self.base = info["base"]
        return info

    def calibrate_palette(self):
        """Scan palette area and map color_id -> client click position."""
        self.window.focus()
        time.sleep(0.3)
        base = self._find_clicktest()
        if not base:
            return
        prev = self.reader.read_int(base + 76)
        positions = {}
        left, top, w, h = self.window.client_rect()
        strip_y = h - 110
        regions = []
        start_x = 120
        for x in range(120, min(w - 50, 520), 12):
            self.controller.click(x, strip_y, duration=0.01)
            time.sleep(0.05)
            sid = self.reader.read_int(base + 76)
            if sid != prev and 1 <= sid <= 99:
                regions.append((start_x, x, prev))
                start_x = x
                prev = sid
        regions.append((start_x, min(w - 50, 520), prev))
        # pick widest region for each color (handles duplicate edge buttons)
        widest = {}
        for sx, ex, col in regions:
            width = ex - sx
            if col not in widest or width > widest[col][0]:
                widest[col] = (width, (sx + ex) // 2, strip_y)
        positions = {col: (cx, strip_y) for col, (_, cx, strip_y) in widest.items() if 1 <= col <= 99}
        self.palette_positions = positions
        self.controller.set_palette_positions(positions)
        print("Palette positions:", positions)

    def _find_clicktest(self):
        """Find ClickTest object by looking for a referencer of CrossLevelStorage."""
        base = self.base or self.grid.find_cross_level_storage(self.book_name, self.save_file)
        if not base:
            return 0
        x_max = self.reader.read_int(base + 76)
        y_max = self.reader.read_int(base + 80)
        ptr_bytes = base.to_bytes(4, "little")
        refs = self.reader.scan_pattern(ptr_bytes)
        for ref in refs:
            cand = ref - 48
            try:
                cx = self.reader.read_int(cand + 80)
                cy = self.reader.read_int(cand + 84)
            except Exception:
                continue
            if cx == x_max and cy == y_max:
                return cand
        return 0

    def _mapping_to_homography(self, mapping):
        if len(mapping) >= 4:
            return HomographyMapper(mapping)
        if not mapping:
            return None
        # Not enough points for a full homography; use a simple affine grid from the first cell and spacing.
        from process.coordinates import CoordinateMapper
        (lx0, ly0), (cx0, cy0) = next(iter(mapping.items()))
        # Try to recover spacing from the mapping.
        dxs = []
        dys = []
        for (lx, ly), (cx, cy) in mapping.items():
            if lx == lx0 and ly != ly0:
                dys.append((cy - cy0) / (ly - ly0))
            if ly == ly0 and lx != lx0:
                dxs.append((cx - cx0) / (lx - lx0))
        dx = dxs[0] if dxs else 54
        dy = dys[0] if dys else 54
        ox = cx0 - lx0 * dx
        oy = cy0 - ly0 * dy
        return CoordinateMapper(ox, oy, dx, dy, self.window.left, self.window.top)

    def _is_sane_calibration(self, mapping, dx, dy):
        """Reject calibrations that come from UI elements instead of the grid."""
        if not mapping or dx is None or dy is None or len(mapping) < 4:
            return False
        if not (10 <= dx <= 120 and 10 <= dy <= 120):
            return False
        # Level grid cells are square-ish; a 1:3 or 3:1 ratio means we hit UI/text.
        ratio = dx / dy if dy else 999
        if ratio < 0.5 or ratio > 2.0:
            return False
        return True

    # Cells must stay large enough for the grid detector, but small enough that a
    # useful number of them fits into one viewport.
    MIN_CELL_PX = 26
    MAX_CELL_PX = 90
    TARGET_CELL_PX = 40

    def _safe_area(self):
        """Client rectangle that belongs to the canvas, excluding the bottom UI bar."""
        return 0, 0, self.window.width, int(self.window.height * 0.86)

    def calibrate_view(self, info=None, max_attempts=10, no_zoom=False,
                       expected_dx=None, expected_dy=None,
                       expected_ox=None, expected_oy=None):
        """Calibrate the current viewport, adjusting zoom until the grid is readable.

        Returns (ox, oy, dx, dy) mapping logical cells to client pixels,
        or None if calibration fails after max_attempts.

        When no_zoom=True, tries a single vision pass without any zoom
        adjustment — used after panning when few cells remain and zoom
        changes would destroy the calibration.

        When expected_dx/expected_dy are provided, they are passed to vision
        as fallback spacing and to filter merged contours.

        When expected_ox/expected_oy are provided, they are used as a prior
        for the origin search (distance penalty in scoring).
        """
        if expected_ox is not None:
            print(f"  [calibrate_view] no_zoom={no_zoom} attempts={max_attempts} "
                  f"expected dx={expected_dx} dy={expected_dy} "
                  f"ox={expected_ox:.0f} oy={expected_oy:.0f}")
        else:
            print(f"  [calibrate_view] initial calibration (no prior)")
        for attempt in range(max_attempts):
            if info is None:
                info = self._read_grids()
            cal = self.vision.calibrate(info["saved"], info["main"],
                                        expected_dx=expected_dx, expected_dy=expected_dy,
                                        expected_ox=expected_ox, expected_oy=expected_oy)
            if cal is not None:
                ox, oy, dx, dy = cal
                if no_zoom:
                    return cal
                if dx < self.MIN_CELL_PX or dy < self.MIN_CELL_PX:
                    print(f"  Cells too small ({dx}x{dy}); zooming in")
                    self.controller.zoom(2)
                elif dx > self.MAX_CELL_PX or dy > self.MAX_CELL_PX:
                    print(f"  Cells too large ({dx}x{dy}); zooming out")
                    self.controller.zoom(-2)
                else:
                    return cal
            else:
                if no_zoom:
                    return None
                # If cells were at the right size, zooming out will only make
                # them smaller and harder to detect — return None so the
                # solver can try a different strategy (e.g. pan to center).
                if (expected_dx is not None and
                        self.MIN_CELL_PX <= expected_dx <= self.MAX_CELL_PX):
                    print(f"  Calibration failed but cells are right size; not zooming")
                    return None
                # Nothing recognisable: most likely zoomed far in or panned away.
                print(f"  Calibration attempt {attempt + 1} failed; zooming out")
                self.controller.zoom(-3)
            info = None
        return None

    def ensure_mapper(self, max_zoom_attempts=8):
        """Backwards-compatible single-viewport calibration."""
        if self.mapper is not None:
            return
        self.window.focus()
        time.sleep(0.3)
        info = self._read_grids()
        mapping, dx, dy = self.vision.build_grid_mapping(info["saved"], info["main"])
        if self._is_sane_calibration(mapping, dx, dy):
            self.mapper = HomographyMapper(mapping)
            print(f"Vision calibrated {len(mapping)} cells, spacing ({dx}, {dy})")
            return
        self.calibrate_view(info)

    def _collect_tasks(self, info=None):
        if info is None:
            info = self._read_grids()
        x_max, y_max = info["x_max"], info["y_max"]
        main = info["main"]
        saved = info["saved"]
        tasks = defaultdict(list)
        for y in range(y_max):
            for x in range(x_max):
                target = main[y][x]
                if target != 0 and saved[y][x] != target:
                    tasks[target].append((x, y))
        return tasks, info

    def _remaining_cells(self, info):
        """All (x, y) that still need painting, as a set."""
        remaining = set()
        for y in range(info["y_max"]):
            for x in range(info["x_max"]):
                if info["main"][y][x] != 0 and info["saved"][y][x] != info["main"][y][x]:
                    remaining.add((x, y))
        return remaining

    def _nearest_remaining(self, remaining, cal):
        """Find the remaining cell closest to the current viewport center."""
        ox, oy, dx, dy = cal
        x0, y0, x1, y1 = self._safe_area()
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        best = None
        best_dist = float('inf')
        for (x, y) in remaining:
            sx = ox + x * dx
            sy = oy + y * dy
            dist = (sx - cx) ** 2 + (sy - cy) ** 2
            if dist < best_dist:
                best_dist = dist
                best = (x, y)
        return best or min(remaining, key=lambda c: (c[1], c[0]))

    def _farthest_remaining(self, remaining, cal):
        """Find the remaining cell farthest from the current viewport center."""
        ox, oy, dx, dy = cal
        x0, y0, x1, y1 = self._safe_area()
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        best = None
        best_dist = -1
        for (x, y) in remaining:
            sx = ox + x * dx
            sy = oy + y * dy
            dist = (sx - cx) ** 2 + (sy - cy) ** 2
            if dist > best_dist:
                best_dist = dist
                best = (x, y)
        return best or min(remaining, key=lambda c: (c[1], c[0]))

    def _densest_remaining(self, remaining, cal):
        """Find the remaining cell with the most other remaining cells nearby.

        Used when the grid is sparse to pan to the densest cluster.
        """
        ox, oy, dx, dy = cal
        x0, y0, x1, y1 = self._safe_area()
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        viewport_w = (x1 - x0) / dx
        viewport_h = (y1 - y0) / dy
        rem_list = list(remaining)
        rem_arr = np.array(rem_list)  # (n, 2)
        # Vectorized: count cells within viewport distance of each cell.
        dx_mat = np.abs(rem_arr[:, 0:1] - rem_arr[:, 0:1].T)  # (n, n)
        dy_mat = np.abs(rem_arr[:, 1:2] - rem_arr[:, 1:2].T)  # (n, n)
        counts = ((dx_mat < viewport_w) & (dy_mat < viewport_h)).sum(axis=1)
        # Prefer dense clusters near current viewport.
        cur_x = (cx - ox) / dx
        cur_y = (cy - oy) / dy
        dist_sq = (rem_arr[:, 0] - cur_x) ** 2 + (rem_arr[:, 1] - cur_y) ** 2
        scores = counts.astype(float) * 100 - dist_sq
        best_idx = scores.argmax()
        return tuple(rem_arr[best_idx])

    def _paint_viewport(self, info, cal, remaining, max_clicks=None):
        """Paint every remaining cell that currently lies inside the canvas.

        Returns the number of cells clicked.
        """
        ox, oy, dx, dy = cal
        x0, y0, x1, y1 = self._safe_area()
        margin = max(4, min(dx, dy) // 4)
        by_color = defaultdict(list)
        for (x, y) in remaining:
            sx = ox + x * dx
            sy = oy + y * dy
            if not (x0 + margin <= sx <= x1 - margin and y0 + margin <= sy <= y1 - margin):
                continue
            by_color[info["main"][y][x]].append((x, y, int(round(sx)), int(round(sy))))
        if not by_color:
            return 0
        clicked = 0
        for color in sorted(by_color):
            self.controller.select_color_by_key(color)
            # Serpentine order keeps the cursor travel short.
            cells = by_color[color]
            cells.sort(key=lambda c: (c[1], c[0] if c[1] % 2 == 0 else -c[0]))
            for _, _, sx, sy in cells:
                if max_clicks is not None and clicked >= max_clicks:
                    return clicked
                self.controller.click(sx, sy, duration=0.01)
                clicked += 1
            time.sleep(0.02)
        return clicked

    def _pan_to(self, cal, target, info):
        """Pan so that `target` (a logical cell) moves to the centre of the canvas.

        Returns (pan_dx, pan_dy, capped) so the caller can adjust the origin.
        `capped` is True if the pan was limited to avoid overshooting.
        """
        ox, oy, dx, dy = cal
        x0, y0, x1, y1 = self._safe_area()
        tx = ox + target[0] * dx
        ty = oy + target[1] * dy
        pan_dx = int(round((x0 + x1) / 2 - tx))
        pan_dy = int(round((y0 + y1) / 2 - ty))
        # Cap pan to 95% of viewport — larger pans often overshoot due to
        # game edge clamping or pan speed limits.
        max_pan_x = int((x1 - x0) * 0.95)
        max_pan_y = int((y1 - y0) * 0.95)
        capped = False
        if abs(pan_dx) > max_pan_x:
            pan_dx = (1 if pan_dx > 0 else -1) * max_pan_x
            capped = True
        if abs(pan_dy) > max_pan_y:
            pan_dy = (1 if pan_dy > 0 else -1) * max_pan_y
            capped = True
        self.controller.pan(pan_dx, pan_dy)
        return pan_dx, pan_dy, capped

    def solve(self, max_viewports=400):
        self.window.focus()
        time.sleep(0.2)
        info = self._read_grids()
        remaining = self._remaining_cells(info)
        total = len(remaining)
        print(f"Level {info['x_max']}x{info['y_max']}, {total} cells to paint")
        if not remaining:
            print("Level already complete.")
            return True

        cal = self.calibrate_view(info)
        if cal is None:
            print("Failed to calibrate vision for this level")
            return False
        print(f"Calibrated: origin ({cal[0]}, {cal[1]}), cell {cal[2]}x{cal[3]}")

        consecutive_stalls = 0
        last_target = None
        stuck_count = 0
        calibration_failed = False
        last_pan_capped = False
        for viewport in range(max_viewports):
            if calibration_failed:
                # Previous quick calibration failed — don't paint with
                # uncertain origin.  Try full recalibration instead.
                print(f"  Skipping paint (calibration uncertain); full recalibration")
                new_cal = self.calibrate_view(info, expected_dx=cal[2], expected_dy=cal[3],
                                               expected_ox=cal[0], expected_oy=cal[1])
                if new_cal is not None:
                    cal = new_cal
                    consecutive_stalls = 0
                    stuck_count = 0
                    calibration_failed = False
                    info = None
                else:
                    stuck_count += 1
                    if stuck_count <= 5:
                        print(f"  Recalibration failed; trying fresh calibration (stuck_count={stuck_count})")
                        new_cal = self.calibrate_view(info, expected_dx=cal[2], expected_dy=cal[3])
                        if new_cal is not None:
                            cal = new_cal
                            consecutive_stalls = 0
                            stuck_count = 0
                            calibration_failed = False
                            info = None
                        else:
                            # Both calibrations failed — we're in an area with
                            # very few uncolored cells.  Pan towards the densest
                            # remaining cluster and try again.
                            if remaining:
                                target = self._densest_remaining(remaining, cal)
                                pan_dx, pan_dy, capped = self._pan_to(cal, target, info)
                                print(f"  Calibration failed; panning to densest cluster "
                                      f"({target[0]},{target[1]}) by ({pan_dx},{pan_dy})"
                                      f"{' [capped]' if capped else ''}")
                                cal = (cal[0] + pan_dx, cal[1] + pan_dy, cal[2], cal[3])
                            else:
                                print("  No remaining cells but calibration failed; giving up")
                                break
                    else:
                        print("  Stuck too many times; giving up")
                        break
                continue
            # Ensure info is fresh (may be None after recalibration).
            if info is None:
                info = self._read_grids()
            if last_pan_capped:
                # Previous pan was capped — we're in transit to a far target.
                # Skip painting and keep panning towards the SAME target.
                last_pan_capped = False
                done = 0
                target = last_target
                print(f"  viewport {viewport + 1}: in transit, skipping paint")
            else:
                # When stalling, limit clicks to avoid mass mispainting.
                max_clicks = 20 if consecutive_stalls > 0 else None
                clicked = self._paint_viewport(info, cal, remaining, max_clicks=max_clicks)
                time.sleep(0.1)
                info = self._read_grids()
                new_remaining = self._remaining_cells(info)
                done = len(remaining) - len(new_remaining)
                remaining = new_remaining
                print(f"  viewport {viewport + 1}: clicked {clicked}, painted {done}, "
                      f"{len(remaining)} left")
                if not remaining:
                    print("Level complete.")
                    return True
                if done < 0:
                    # Cells were un-painted — calibration is wrong.
                    print("  Un-painting detected; calibration uncertain")
                    calibration_failed = True
                    continue
                if done <= 0 or (clicked > 20 and done < clicked * 0.05):
                    consecutive_stalls += 1
                    if consecutive_stalls > self.max_retries:
                        print(f"  Stalling (consecutive={consecutive_stalls}); calibration uncertain")
                        calibration_failed = True
                        continue
                else:
                    consecutive_stalls = 0
                    stuck_count = 0
                # Select next target.
                x0, y0, x1, y1 = self._safe_area()
                viewport_capacity = int((x1 - x0) / cal[2]) * int((y1 - y0) / cal[3])
                if len(remaining) <= viewport_capacity:
                    target = self._densest_remaining(remaining, cal)
                else:
                    target = self._nearest_remaining(remaining, cal)
                # If we're stuck on the same target, try a different one.
                if target == last_target and done <= 0:
                    # Pick the farthest remaining cell instead to force a big pan.
                    target = self._farthest_remaining(remaining, cal)
                    print(f"  Same target stuck; trying farthest cell instead")
                last_target = target
            pan_dx, pan_dy, capped = self._pan_to(cal, target, info)
            print(f"  Panning to ({target[0]},{target[1]}) by ({pan_dx},{pan_dy})"
                  f"{' [capped]' if capped else ''}")
            if capped:
                # Pan was capped — target is still far away.
                # Update origin estimate and keep panning towards it.
                # Skip painting on next iteration to avoid mispainting.
                cal = (cal[0] + pan_dx, cal[1] + pan_dy, cal[2], cal[3])
                last_pan_capped = True
                continue
            info = self._read_grids()
            # Quick calibration: one attempt, no zoom changes, with expected spacing.
            pan_cal = (cal[0] + pan_dx, cal[1] + pan_dy, cal[2], cal[3])
            new_cal = self.calibrate_view(info, max_attempts=1, no_zoom=True,
                                           expected_dx=cal[2], expected_dy=cal[3],
                                           expected_ox=pan_cal[0], expected_oy=pan_cal[1])
            if new_cal is not None:
                # Trust vision if within 3 cells of pan-adjusted position.
                # Use vision origin (more accurate than pan), but keep old dx/dy.
                # 3-cell tolerance: the game's pan can be off by up to 3 cells
                # due to edge clamping or speed limits.
                tol_x = cal[2] * 3
                tol_y = cal[3] * 3
                if abs(new_cal[0] - pan_cal[0]) <= tol_x and abs(new_cal[1] - pan_cal[1]) <= tol_y:
                    cal = (new_cal[0], new_cal[1], cal[2], cal[3])
                else:
                    # Vision disagrees significantly — don't trust either.
                    print(f"  Vision origin off by ({new_cal[0] - pan_cal[0]}, {new_cal[1] - pan_cal[1]}); will recalibrate")
                    cal = pan_cal
                    calibration_failed = True
            else:
                print(f"  Vision failed; will recalibrate on next iteration")
                cal = pan_cal
                calibration_failed = True
        print(f"Failed to complete level, remaining: {len(remaining)}")
        return False


if __name__ == "__main__":
    s = Solver()
    s.solve()
