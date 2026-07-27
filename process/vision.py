"""Detect grid cell centers from the game window using OpenCV."""
import cv2
import numpy as np
import mss
from pathlib import Path


class Vision:
    def __init__(self, window_rect):
        # window_rect: (left, top, width, height) of the game client area
        self.left, self.top, self.width, self.height = window_rect

    def capture(self):
        with mss.MSS() as sct:
            monitor = {"left": self.left, "top": self.top, "width": self.width, "height": self.height}
            img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def detect_uncolored_cells(self, min_area=225, max_area=20000):
        """Return list of (cx, cy, w, h) for uncolored cells."""
        img = self.capture()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # uncolored cells have dark interior; colored cells are bright
        _, thresh = cv2.threshold(gray, 40, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cells = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area or area > max_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            if w < 15 or h < 15 or abs(w - h) > max(w, h) * 0.3:
                continue
            cx = x + w // 2
            cy = y + h // 2
            cells.append((cx, cy, w, h))
        return cells

    def _filter_by_expected_size(self, cells, expected_dx, expected_dy):
        """Keep only cells whose w/h are close to the expected cell size.

        This removes merged contours and UI elements that corrupt spacing.
        """
        if not cells or expected_dx is None or expected_dy is None:
            return cells
        ew = expected_dx
        eh = expected_dy
        tol = max(ew, eh) * 0.5
        filtered = []
        for cx, cy, w, h in cells:
            if abs(w - ew) <= tol and abs(h - eh) <= tol:
                filtered.append((cx, cy, w, h))
        return filtered if filtered else cells

    def _spacing_close(self, dx, dy, expected_dx, expected_dy, tol=0.3):
        """Check if estimated spacing is close to expected."""
        if expected_dx is None or expected_dy is None:
            return True
        return (abs(dx - expected_dx) <= expected_dx * tol and
                abs(dy - expected_dy) <= expected_dy * tol)

    def _estimate_spacing(self, cells):
        xs = sorted({c[0] for c in cells})
        ys = sorted({c[1] for c in cells})

        def cluster(vals, tol=20):
            if not vals:
                return []
            vals = sorted(vals)
            groups = [[vals[0]]]
            for v in vals[1:]:
                if v - groups[-1][-1] <= tol:
                    groups[-1].append(v)
                else:
                    groups.append([v])
            return [sum(g) / len(g) for g in groups]

        x_lines = cluster(xs, 25)
        y_lines = cluster(ys, 25)
        if len(x_lines) < 2 or len(y_lines) < 2:
            return None, None
        dx = int(round(np.median(np.diff(x_lines))))
        dy = int(round(np.median(np.diff(y_lines))))
        return dx, dy

    def calibrate(self, saved_grid, main_grid, expected_dx=None, expected_dy=None,
                  expected_ox=None, expected_oy=None):
        """Return (ox, oy, dx, dy) for mapping logical (x,y) to screen center (ox+x*dx, oy+y*dy).

        The detected cells are dark (uncolored), so they should map to logical
        positions where saved == -1 and main != 0.  Scoring against this
        uncolored pattern is far more discriminating than checking main != 0
        alone, which matches almost any offset on a large grid.

        If expected_dx/expected_dy are provided, they are used as fallback
        spacing when estimation from detected cells fails (e.g. too few
        cells or merged contours).

        If expected_ox/expected_oy are provided, a distance penalty is applied
        to the scoring so candidates near the expected origin win ties.  This
        is crucial after panning where the pan-adjusted origin is a good
        approximation.  When not provided, a prior is auto-computed from the
        detected cells' bounding box: if the entire grid is visible, the
        top-left cell maps to (0,0); otherwise a centering heuristic is used.
        """
        cells = self.detect_uncolored_cells()
        # Filter out UI elements at the bottom and extreme edges
        max_y = int(self.height * 0.85)
        cells = [c for c in cells if 100 < c[0] < self.width - 50 and 20 < c[1] < max_y]
        if not cells:
            return None
        # If we know the expected cell size, filter out merged contours.
        if expected_dx is not None and expected_dy is not None:
            cells = self._filter_by_expected_size(cells, expected_dx, expected_dy)
            print(f"  [vision] after size filter: {len(cells)} cells")
        dx, dy = self._estimate_spacing(cells)
        print(f"  [vision] estimated spacing: dx={dx} dy={dy}")
        if dx is None or dx < 20 or dy < 20:
            # Fall back to expected spacing if available.
            if expected_dx is not None and expected_dy is not None:
                dx, dy = expected_dx, expected_dy
                print(f"  [vision] spacing fallback to expected: dx={dx} dy={dy}")
            else:
                return None
        elif not self._spacing_close(dx, dy, expected_dx, expected_dy):
            # Estimated spacing is way off (e.g. merged contours) — use expected.
            print(f"  [vision] spacing sanity check failed; using expected dx={expected_dx} dy={expected_dy}")
            dx, dy = expected_dx, expected_dy

        y_max = len(saved_grid)
        x_max = len(saved_grid[0]) if y_max else 0

        # Boolean mask of logical positions that still need painting.
        # This includes both truly uncolored cells (saved == -1) and
        # wrong-colored cells (saved != main).  Wrong-colored DARK cells
        # are detected by vision as uncolored, so they must be in the
        # mask for pattern matching to work correctly.
        uncolored_mask = np.zeros((y_max, x_max), dtype=bool)
        for y in range(y_max):
            for x in range(x_max):
                if main_grid[y][x] != 0 and saved_grid[y][x] != main_grid[y][x]:
                    uncolored_mask[y, x] = True
        if not uncolored_mask.any():
            return None
        n_uncolored = int(uncolored_mask.sum())
        print(f"  [vision] grid {x_max}x{y_max}, {n_uncolored} uncolored in pattern, "
              f"{len(cells)} detected on screen")

        # Pick a stable reference cell near the median of detected cells.
        cx_vals = [c[0] for c in cells]
        cy_vals = [c[1] for c in cells]
        mx = int(np.median(cx_vals))
        my = int(np.median(cy_vals))
        ref = min(cells, key=lambda c: (c[0] - mx) ** 2 + (c[1] - my) ** 2)
        rx, ry = ref[0], ref[1]

        # Relative grid offsets of all detected cells from the reference.
        cell_pts = np.array([(c[0], c[1]) for c in cells])
        rel_gx = np.round((cell_pts[:, 0] - rx) / dx).astype(int)
        rel_gy = np.round((cell_pts[:, 1] - ry) / dy).astype(int)

        # The reference cell is uncolored, so it must map to an uncolored
        # logical position.  Try only those candidates.
        candidates = np.argwhere(uncolored_mask)  # each row: [ly, lx]
        lx_arr = candidates[:, 1].astype(int)
        ly_arr = candidates[:, 0].astype(int)

        # Compute expected origin if not provided.
        if expected_ox is None or expected_oy is None:
            # Estimate from detected cells' bounding box.
            min_cx = min(c[0] for c in cells)
            min_cy = min(c[1] for c in cells)
            max_cx = max(c[0] for c in cells)
            max_cy = max(c[1] for c in cells)
            num_cols = round((max_cx - min_cx) / dx) + 1
            num_rows = round((max_cy - min_cy) / dy) + 1

            if num_cols == x_max and num_rows == y_max:
                # Entire grid visible — top-left cell maps to (0,0).
                expected_ox = float(min_cx)
                expected_oy = float(min_cy)
                print(f"  [vision] auto-prior: full grid visible, "
                      f"origin=({expected_ox:.0f},{expected_oy:.0f})")
            else:
                # Partially visible — grid is centered at viewport center
                # (game centers grid on load).  Use viewport center, not
                # detected-cells center, because margin filtering biases the
                # detected center away from the true viewport center.
                expected_ox = self.width / 2 - (x_max - 1) * dx / 2
                expected_oy = self.height / 2 - (y_max - 1) * dy / 2
                print(f"  [vision] auto-prior: partial grid "
                      f"({num_cols}x{num_rows} of {x_max}x{y_max}), "
                      f"bbox=({min_cx:.0f},{min_cy:.0f})-({max_cx:.0f},{max_cy:.0f}), "
                      f"viewport=({self.width}x{self.height}), "
                      f"origin=({expected_ox:.0f},{expected_oy:.0f})")
        else:
            print(f"  [vision] using provided prior: "
                  f"({expected_ox:.0f},{expected_oy:.0f})")

        use_prior = True

        best = None
        best_score = -1e9
        batch_size = 4000
        cell_size = max(dx, dy)
        for start in range(0, len(candidates), batch_size):
            end = start + batch_size
            lx_b = lx_arr[start:end]
            ly_b = ly_arr[start:end]
            # gx[c, i] = lx_b[c] + rel_gx[i]
            gx = lx_b[:, None] + rel_gx[None, :]
            gy = ly_b[:, None] + rel_gy[None, :]
            valid = (gx >= 0) & (gx < x_max) & (gy >= 0) & (gy < y_max)
            gx_safe = np.where(valid, gx, 0)
            gy_safe = np.where(valid, gy, 0)
            hits = (uncolored_mask[gy_safe, gx_safe] & valid).sum(axis=1)
            scores = 2 * hits - valid.sum(axis=1)
            if use_prior:
                # Distance penalty: prefer candidates near expected origin.
                # 1.0 per cell of distance — strong enough to break ties when
                # the uncolored pattern is uniform (multiple origins give the
                # same hit count).  Score per hit is 2, so 1.0 penalty still
                # allows vision to correct pan errors of up to 1 cell.
                cand_ox = rx - lx_b.astype(float) * dx
                cand_oy = ry - ly_b.astype(float) * dy
                dist_cells = np.sqrt((cand_ox - expected_ox) ** 2 +
                                     (cand_oy - expected_oy) ** 2) / cell_size
                scores = scores - dist_cells * 1.0
            idx = scores.argmax()
            if scores[idx] > best_score:
                best_score = float(scores[idx])
                best = (int(rx - lx_b[idx] * dx), int(ry - ly_b[idx] * dy))

        if best is None or best_score < max(2, len(cells) // 4):
            # Main search failed — likely the reference cell was a false
            # positive (e.g. a dark gap or a wrongly-coloured cell that's
            # no longer in the uncolored_mask).  Try a local brute-force
            # search around the expected origin instead.
            if expected_ox is not None and expected_oy is not None:
                print(f"  [vision] main search failed (best_score={best_score:.1f}); "
                      f"trying local search around ({expected_ox:.0f},{expected_oy:.0f})")
                sr = int(2 * max(dx, dy))
                cx_arr = cell_pts[:, 0]
                cy_arr = cell_pts[:, 1]
                best_local = None
                best_local_score = -1e9
                # Coarse search: step by 2px, then refine.
                for step in [2, 1]:
                    if step == 2:
                        oxs = range(int(expected_ox) - sr, int(expected_ox) + sr + 1, 2)
                        oys = range(int(expected_oy) - sr, int(expected_oy) + sr + 1, 2)
                    else:
                        if best_local is None:
                            break
                        oxs = range(best_local[0] - 3, best_local[0] + 4)
                        oys = range(best_local[1] - 3, best_local[1] + 4)
                    for ox in oxs:
                        for oy in oys:
                            gx = np.round((cx_arr - ox) / dx).astype(int)
                            gy = np.round((cy_arr - oy) / dy).astype(int)
                            valid = (gx >= 0) & (gx < x_max) & (gy >= 0) & (gy < y_max)
                            if valid.any():
                                hits = int((uncolored_mask[gy[valid], gx[valid]]).sum())
                            else:
                                hits = 0
                            if hits > best_local_score:
                                best_local_score = hits
                                best_local = (ox, oy)
                if best_local is not None and best_local_score >= max(2, len(cells) // 4):
                    print(f"  [vision] local search: origin=({best_local[0]},{best_local[1]}) "
                          f"score={best_local_score}")
                    return (*best_local, dx, dy)
                print(f"  [vision] local search also failed (best_score={best_local_score})")
            return None

        print(f"  [vision] cells={len(cells)} dx={dx} dy={dy} "
              f"cands={len(candidates)} best_score={best_score:.1f} "
              f"origin=({best[0]},{best[1]}) "
              f"expected=({expected_ox:.0f},{expected_oy:.0f})")

        # Refine with small pixel offsets for sub-pixel accuracy.
        ox0, oy0 = best
        for ox in range(ox0 - 3, ox0 + 4):
            for oy in range(oy0 - 3, oy0 + 4):
                score = 0
                for cx, cy, _, _ in cells:
                    gx = int(round((cx - ox) / dx))
                    gy = int(round((cy - oy) / dy))
                    if 0 <= gx < x_max and 0 <= gy < y_max and uncolored_mask[gy, gx]:
                        score += 1
                if use_prior:
                    dist_pen = 0.1 * (((ox - expected_ox) ** 2 + (oy - expected_oy) ** 2) ** 0.5) / cell_size
                    score -= dist_pen
                if score > best_score:
                    best_score = score
                    best = (ox, oy)
        return (*best, dx, dy)

    def build_grid_mapping(self, saved_grid, main_grid):
        """Map logical (x,y) to screen (cx,cy) using the saved grid pattern."""
        cal = self.calibrate(saved_grid, main_grid)
        if cal is None:
            return {}, None, None
        ox, oy, dx, dy = cal
        y_max = len(saved_grid)
        x_max = len(saved_grid[0]) if y_max else 0
        mapping = {}
        for y in range(y_max):
            for x in range(x_max):
                if saved_grid[y][x] == -1 and main_grid[y][x] != 0:
                    mapping[(x, y)] = (int(ox + x * dx), int(oy + y * dy))
        return mapping, dx, dy


if __name__ == "__main__":
    import json, sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from process.grid_reader import GridReader, MemoryReader
    r = MemoryReader(process_name="ColoringPixels.exe")
    gr = GridReader(r)
    info = gr.read_grids()
    vis = Vision((120, 26, 1680, 1050))
    cells = vis.detect_uncolored_cells()
    print("detected cells", len(cells))
    mapping, dx, dy = vis.build_grid_mapping(info["saved"], info["main"])
    print("mapping size", len(mapping), "dx", dx, "dy", dy)
    for (x, y), (cx, cy) in list(mapping.items())[:10]:
        print(x, y, "->", cx, cy)
