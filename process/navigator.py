"""Navigate the Coloring Pixels menu/book/level UI.

This implementation targets 1920x1080 fullscreen. UI coordinates live in
data/ui_config.json and can be refined per resolution.
"""
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import ctypes
import numpy as np
import cv2

from process.input_controller import InputController
from process.window_manager import WindowManager
from process.memory_reader import MemoryReader
from process.grid_reader import GridReader
from process.vision import Vision


class Navigator:
    def __init__(self, window_rect=None, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "data" / "ui_config.json"
        with open(config_path) as f:
            self.cfg = json.load(f)
        self.window = WindowManager()
        self.window.update_rect()
        self.controller = InputController(self.window.client_rect())
        self.left, self.top, self.width, self.height = self.window.client_rect()
        self.scrolled = 1.0  # normalized scroll position (1 = top)
        # Absolute card row of the first *detected* OPEN button row when the list
        # is scrolled to the top. The very first row is often clipped, so this is
        # learned from memory feedback the first time a wrong level opens.
        self._top_row_offset = 0
        self._scroll_accum = 0.0
        # Learned mapping from a sidebar button's y position to its book hash.
        self._sidebar_map = {}
        self.reader = MemoryReader(process_name="ColoringPixels.exe")
        self.grid = GridReader(self.reader)
        self.level_base = 0
        self.levels_data = json.load(open(Path(__file__).parent.parent / "data" / "levels.json"))
        # Sidebar order: the game sorts books by bookType then bookIndex.
        type_order = {"None": 0, "Free": 1, "Bonus": 2, "DLC": 3, "Reward": 4}
        sorted_books = sorted(
            self.levels_data.items(),
            key=lambda kv: (type_order.get(str(kv[1].get("book_type", "Free")), 99), kv[1].get("book_index", 0))
        )
        self.title_to_book = {b["main_menu_title"]: key for key, b in sorted_books}
        self.book_titles = [b["main_menu_title"] for key, b in sorted_books]
        # Anchors used to locate the live CrossLevelStorage via lastBookOpenHash.
        self._book_hashes = [b["book_hash"] for _, b in sorted_books if b.get("book_hash") is not None]
        if not self.book_titles:
            # Fallback to ui_config list/dict if levels.json has no metadata yet.
            titles = self.cfg["sidebar"]["book_titles"]
            self.book_titles = list(titles.keys()) if isinstance(titles, dict) else list(titles)

    def _cfg_client(self, key, default=None):
        return self.cfg.get(key, default)

    def focus(self):
        self.window.focus()
        time.sleep(0.3)

    def click_client(self, x, y, duration=0.05):
        """Click at client-relative coordinates."""
        self.controller.click(x, y, duration=duration)

    def _detect_sidebar_buttons(self, img=None):
        """Detect book buttons in the left sidebar. Returns list of (cx, cy) sorted top-to-bottom."""
        if img is None:
            img = self._screenshot()
        side = self.cfg["sidebar"]
        # Sidebar region is the left column of the screen.
        roi = img[:, :side.get("sidebar_right", 420)]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # The buttons are white on a beige panel, so match their dark outlines.
        _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        left = side.get("button_left", 20)
        right = side.get("button_right", 410)
        buttons = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w < 200 or h < 40 or h > 120:
                continue
            if w / h < 2.5 or w / h > 9.0:
                continue
            # Must sit inside the sidebar column. Level cards animating in from the
            # right can otherwise clip into this region and look like book buttons.
            if x < left - 15 or x + w > right:
                continue
            # avoid the bottom icon bar
            if y > self.height * 0.9:
                continue
            cx, cy = x + w // 2, y + h // 2
            # skip the inner fill contour of a button we already matched
            if any(abs(cy - by) < 25 for _, by in buttons):
                continue
            buttons.append((cx, cy))
        buttons.sort(key=lambda b: b[1])
        return buttons

    def live_base(self):
        """Address of the live CrossLevelStorage, valid in any scene."""
        return self.grid.find_storage(self._book_hashes)

    def current_book_hash(self):
        """Hash of the book currently shown in the level select, or None."""
        base = self.live_base()
        if not base:
            return None
        return self.grid.read_last_book_hash(base)

    def _scroll_sidebar(self, direction, ticks=3):
        side = self.cfg["sidebar"]
        sx, sy = self.controller._to_screen(side.get("scroll_x", 215), self.height // 2)
        ctypes.windll.user32.SetCursorPos(sx, sy)
        time.sleep(0.1)
        for _ in range(ticks):
            ctypes.windll.user32.mouse_event(0x0800, 0, 0, direction * -120, 0)
            time.sleep(0.05)
        time.sleep(0.4)

    def wait_for_level_select(self, timeout=8):
        """Wait until the level cards have finished animating into place."""
        end = time.time() + timeout
        while time.time() < end:
            if self._detect_open_buttons():
                return True
            time.sleep(0.3)
        return False

    def goto_book(self, book_title, max_probes=40):
        """Select a book in the sidebar, verifying the choice against memory.

        The sidebar only lists the books the player can actually open, so its
        order does not match levels.json. Each candidate button is therefore
        clicked and confirmed via lastBookOpenHash, and the resulting
        button -> book mapping is remembered for later lookups.
        """
        book_key = self.title_to_book.get(book_title)
        if not book_key:
            raise ValueError(f"Unknown book title: {book_title}")
        target_hash = self.levels_data[book_key].get("book_hash")

        self.wait_for_level_select()
        if self.current_book_hash() == target_hash and self._detect_open_buttons():
            return True

        for _ in range(max_probes):
            buttons = self._detect_sidebar_buttons()
            if not buttons:
                raise RuntimeError("No book buttons visible in the sidebar")
            # Prefer a button we already know maps to the target book.
            known = [b for b in buttons if self._sidebar_map.get(b[1]) == target_hash]
            candidates = known or [b for b in buttons if b[1] not in self._sidebar_map]
            if not candidates:
                # Everything visible is mapped to other books; scroll for more.
                self._scroll_sidebar(1)
                continue
            x, y = candidates[0]
            self.click_client(x, y)
            time.sleep(0.6)
            found = self.current_book_hash()
            if found is not None:
                self._sidebar_map[y] = found
            if found == target_hash:
                self.scrolled = 1.0
                self.wait_for_level_select()
                return True
        raise RuntimeError(f"Could not select book {book_title} in the sidebar")

    def _level_row_col(self, level_index, columns):
        return divmod(level_index, columns)

    def _open_button_pos(self, row, col):
        ls = self.cfg["level_select"]
        x = ls["panel_left"] + col * (ls["card_width"] + ls["gap_x"]) + ls["open_offset_x"]
        y = ls["panel_top"] + row * (ls["card_height"] + ls["gap_y"]) + ls["open_offset_y"]
        return x, y

    def _screenshot(self):
        """Capture the game client area as a BGR numpy array."""
        import mss
        with mss.MSS() as sct:
            monitor = {"left": self.left, "top": self.top, "width": self.width, "height": self.height}
            img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def _detect_open_buttons(self, img=None):
        """Detect OPEN buttons by picking the bottommost rectangular child contour in each level card."""
        if img is None:
            img = self._screenshot()
        ls = self.cfg["level_select"]
        roi = img[ls["panel_top"]:ls["panel_bottom"], ls["panel_left"]:ls["panel_right"]]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:
            return []
        # Build a map from parent index to child indices.
        children = {}
        for i, h in enumerate(hierarchy[0]):
            parent = h[3]
            if parent >= 0:
                children.setdefault(parent, []).append(i)
        buttons = []
        for i, c in enumerate(contours):
            # Outer card contours: large, roughly square white cards.
            x, y, w, h = cv2.boundingRect(c)
            if w < 150 or h < 150 or w / h < 0.5 or w / h > 1.5:
                continue
            if w * h < 40000:
                continue
            # The OPEN button is the only child that spans almost the whole card
            # width and sits at the bottom; artwork inside the card never does.
            candidates = []
            for child_idx in children.get(i, []):
                bx, by, bw, bh = cv2.boundingRect(contours[child_idx])
                if bw < 0.85 * w:
                    continue
                if bh < 18 or bw / bh < 3.0 or bw / bh > 12.0:
                    continue
                if by < y + h * 0.75:
                    continue
                candidates.append((by + bh, bx, by, bw, bh))
            if not candidates:
                continue
            candidates.sort(reverse=True)
            _, bx, by, bw, bh = candidates[0]
            cx = ls["panel_left"] + bx + bw // 2
            cy = ls["panel_top"] + by + bh // 2
            # The same button can be reached through nested card contours.
            if any(abs(cx - ox) < 30 and abs(cy - oy) < 30 for ox, oy, _, _ in buttons):
                continue
            buttons.append((cx, cy, bw, bh))
        # Sort by y then x
        buttons.sort(key=lambda b: (b[1], b[0]))
        print(f"    Detected {len(buttons)} OPEN button candidates")
        return [(b[0], b[1]) for b in buttons]

    def _detect_dialog_buttons(self, img=None):
        """Detect the buttons of a modal confirmation dialog in the bottom bar.

        The game shows destructive confirmations (e.g. "DELETE SAVE?") as two
        side-by-side buttons. The affirmative one is on the left, the cancelling
        one on the right, so callers must always pick the rightmost.
        """
        if img is None:
            img = self._screenshot()
        y0 = max(0, self.height - 140)
        roi = img[y0:self.height, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # The buttons are white on a white panel, so match their dark outlines.
        _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        buttons = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            # Level card OPEN buttons are much wider (~340 px), so keep this tight.
            if not (150 <= w <= 260 and 30 <= h <= 70):
                continue
            if w / h < 3.0 or w / h > 6.5:
                continue
            # dialog buttons sit around the horizontal centre of the screen
            cx = x + w // 2
            if not (self.width * 0.25 < cx < self.width * 0.75):
                continue
            cy = y0 + y + h // 2
            # skip the inner fill contour of a button we already matched
            if any(abs(cx - bx) < 40 and abs(cy - by) < 20 for bx, by, _, _ in buttons):
                continue
            buttons.append((cx, cy, w, h))
        buttons.sort(key=lambda b: b[0])
        if len(buttons) != 2:
            return []
        (lx, ly, lw, lh), (rx, ry, rw, rh) = buttons
        # The two buttons are the same size, side by side and centred together.
        if abs(lw - rw) > max(lw, rw) * 0.15 or abs(ly - ry) > 15:
            return []
        gap = (rx - rw // 2) - (lx + lw // 2)
        if not (0 <= gap <= 120):
            return []
        if abs((lx + rx) / 2 - self.width / 2) > 80:
            return []
        return buttons

    def dismiss_dialog(self, img=None):
        """If a confirmation dialog is open, cancel it. Returns True if dismissed."""
        buttons = self._detect_dialog_buttons(img)
        if len(buttons) != 2:
            return False
        cx, cy, _, _ = buttons[-1]  # rightmost == cancel / no
        print(f"  Confirmation dialog detected; clicking CANCEL at ({cx}, {cy})")
        self.click_client(cx, cy)
        time.sleep(0.8)
        return True

    def _scroll_level_panel(self, direction, ticks=4):
        """Wheel-scroll the level select panel. direction 1 = down, -1 = up.

        Scrolling inside a level zooms the camera instead, so this refuses to run
        unless the menu sidebar is on screen.
        """
        if not self.in_menu():
            raise RuntimeError("Refusing to scroll: the level select is not open")
        ls = self.cfg["level_select"]
        panel_cx = (ls["panel_left"] + ls["panel_right"]) // 2
        panel_cy = (ls["panel_top"] + ls["panel_bottom"]) // 2
        sx, sy = self.controller._to_screen(panel_cx, panel_cy)
        ctypes.windll.user32.SetCursorPos(sx, sy)
        time.sleep(0.1)
        for _ in range(ticks):
            ctypes.windll.user32.mouse_event(0x0800, 0, 0, direction * -120, 0)
            time.sleep(0.05)
        time.sleep(0.4)

    def _detect_open_button_rows(self, img=None):
        """Group detected OPEN buttons into rows, each sorted left to right."""
        buttons = self._detect_open_buttons(img)
        rows = []
        for x, y in buttons:
            if rows and abs(y - rows[-1][0][1]) < 80:
                rows[-1].append((x, y))
            else:
                rows.append([(x, y)])
        for row in rows:
            row.sort()
        return rows

    def _row_pitch(self, rows):
        """Vertical distance between two card rows, in pixels."""
        if len(rows) >= 2:
            return abs(rows[1][0][1] - rows[0][0][1])
        return self.cfg["level_select"].get("row_pitch", 610)

    def _scroll_to_edge(self, direction, max_steps=40):
        """Scroll the level list until it stops moving. direction 1 = bottom, -1 = top."""
        last_y = None
        for _ in range(max_steps):
            rows = self._detect_open_button_rows()
            y = rows[0][0][1] if rows else None
            if y is not None and y == last_y:
                break
            last_y = y
            self._scroll_level_panel(direction, ticks=3)
        self.scrolled = 1.0 if direction < 0 else 0.0

    def _scroll_to_top(self, max_steps=40):
        self._scroll_to_edge(-1, max_steps)

    def _scroll_to_bottom(self, max_steps=60):
        self._scroll_to_edge(1, max_steps)

    def _detect_rows_settled(self, tries=4):
        """Detect card rows, nudging the list slightly if none are fully visible.

        A card is only detected while it fits entirely on screen, so a scroll
        position between two rows can yield nothing.
        """
        for i in range(tries):
            rows = self._detect_open_button_rows()
            if rows:
                return rows
            self._scroll_level_panel(1 if i % 2 == 0 else -1, ticks=1)
        return []

    def _find_open_button(self, target_index, total_levels):
        """Return (position, absolute_row) of the OPEN button for a level index.

        Scrolling is done in measured pixels: one wheel tick moves the list by
        ``scroll_px_per_tick`` and consecutive card rows are ``row_pitch`` apart.
        The last rows are addressed from the bottom of the list, because the panel
        clamps there and the pixel model would overshoot.
        """
        ls = self.cfg["level_select"]
        cols = ls["columns"]
        pitch = ls.get("row_pitch", 610)
        px_per_tick = ls.get("scroll_px_per_tick", 100)
        total_rows = max(1, -(-total_levels // cols))
        target_row, target_col = divmod(target_index, cols)

        if target_row >= total_rows - 1:
            self._scroll_to_bottom()
            rows = self._detect_rows_settled()
            if not rows:
                raise RuntimeError(f"No level cards visible for index {target_index}")
            wanted = len(rows) - 1 - (total_rows - 1 - target_row)
            if not (0 <= wanted < len(rows)) or target_col >= len(rows[wanted]):
                raise RuntimeError(f"Could not find OPEN button for level index {target_index}")
            pos = rows[wanted][target_col]
            print(f"  Level {target_index} -> row {target_row} col {target_col} "
                  f"(from bottom); clicking {pos}")
            return pos, target_row

        self._scroll_to_top()
        rows = self._detect_rows_settled()
        if not rows:
            raise RuntimeError(f"No level cards visible for index {target_index}")
        top_y = rows[0][0][1]

        needed_px = (target_row - self._top_row_offset) * pitch
        ticks = int(round(needed_px / float(px_per_tick)))
        if ticks:
            self._scroll_level_panel(1 if ticks > 0 else -1, ticks=abs(ticks))
            rows = self._detect_rows_settled()
            if not rows:
                raise RuntimeError(f"No level cards visible for index {target_index}")
        # After scrolling exactly one row pitch per row, the target row sits where
        # the first row was; pick whichever detected row is closest to that.
        row = min(rows, key=lambda r: abs(r[0][1] - top_y))
        if target_col >= len(row):
            raise RuntimeError(f"Could not find OPEN button for level index {target_index}")
        pos = row[target_col]
        print(f"  Level {target_index} -> row {target_row} col {target_col}; "
              f"scrolled {ticks} ticks; clicking {pos}")
        return pos, target_row

    def _wait_for_loaded_level(self, book_key, timeout=15):
        """Return (level_index, base) of the level the game currently has loaded.

        A fresh CrossLevelStorage is created on every scene load and the previous
        one is destroyed, so the address must never be cached across scenes; the
        destroyed leftovers are filtered out via Unity's m_CachedPtr.
        """
        book_index = self.levels_data[book_key].get("book_index", 0)
        end = time.time() + timeout
        while True:
            base = self.live_base()
            if base and self.grid.read_book_index(base) == book_index:
                self.level_base = base
                return self.grid.read_level_index(base), base
            if time.time() >= end:
                return None, 0
            time.sleep(0.5)

    def goto_level(self, book_title, level_index, max_attempts=4):
        """Open the target level, correcting the button index if the wrong one opens.

        OPEN button detection can pick up a spurious card, which shifts the
        row-major index. Instead of trusting the detection, we read the levelIndex
        the game actually loaded and retry with a corrected offset.
        """
        book_key = self.title_to_book.get(book_title)
        if not book_key:
            raise ValueError(f"Unknown book title: {book_title}")
        book_info = self.levels_data[book_key]
        book_index = book_info.get("book_index", 0)
        levels = book_info["levels"]
        if not 0 <= level_index < len(levels):
            raise IndexError(f"{book_title} has no level index {level_index}")
        level = levels[level_index]

        cols = self.cfg["level_select"]["columns"]
        # Scrolling while still inside a level would zoom the level camera.
        if not self.in_menu() and not self.return_to_menu():
            raise RuntimeError("Could not get back to the menu before selecting a level")
        self.goto_book(book_title)
        for attempt in range(max_attempts):
            (cx, cy), assumed_row = self._find_open_button(level_index, len(levels))
            self.click_client(cx, cy)
            time.sleep(1.0)

            actual_level, base = self._wait_for_loaded_level(book_key)
            if not base:
                raise RuntimeError(
                    f"Could not locate a live CrossLevelStorage after opening "
                    f"{book_title} index {level_index}; is the level actually loaded?"
                )
            if actual_level == level_index:
                print(f"  Level {level_index} ({level['display_name']}) loaded @ 0x{base:08X}")
                return base

            # We landed on a different card row than assumed, so the first
            # detected row at the top of the list is not row 0. Correct that
            # offset; it is a property of the layout and holds for later levels.
            correction = actual_level // cols - assumed_row
            if correction:
                self._top_row_offset += correction
                print(f"  Wrong level opened (index {actual_level}); "
                      f"top row offset -> {self._top_row_offset}")
            else:
                print(f"  Wrong level opened (index {actual_level}) in the expected row; retrying")
            self.return_to_menu()
            self.goto_book(book_title)

        raise RuntimeError(
            f"Could not open {book_title} level {level_index} ({level['display_name']}) "
            f"after {max_attempts} attempts"
        )

    def in_menu(self, img=None):
        """True when the book sidebar is visible, i.e. we are on a menu screen."""
        return bool(self._detect_sidebar_buttons(img))

    def return_to_menu(self, attempts=3):
        """Click the bottom-left X button to exit a level and confirm we reached the menu.

        The delete-save trash icon sits directly above this button, so any
        confirmation dialog that appears is cancelled rather than accepted.
        """
        lv = self.cfg["level"]
        for attempt in range(attempts):
            img = self._screenshot()
            if self.dismiss_dialog(img):
                continue
            if self.in_menu(img):
                return True
            self.click_client(lv["back_button_x"], lv["back_button_y"])
            time.sleep(2.0)
            # Never leave a destructive confirmation open.
            self.dismiss_dialog()
            if self.in_menu():
                return True
        return self.in_menu()
