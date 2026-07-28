"""Low-level input simulation for the game window."""
import ctypes
import time

import numpy as np
import pydirectinput

pydirectinput.FAILSAFE = False

VK_ESCAPE = 0x1B
VK_F12 = 0x7B
VK_SHIFT = 0x10
KEYEVENTF_KEYUP = 0x0002
MOUSE_LEFTDOWN = 0x0002
MOUSE_LEFTUP = 0x0004
MOUSE_RIGHTDOWN = 0x0008
MOUSE_RIGHTUP = 0x0010
_VK_DIGITS = {str(i): 0x30 + i for i in range(10)}


def abort_requested():
    """Return True if the user is holding Escape or F12."""
    user32 = ctypes.windll.user32
    return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000) or bool(user32.GetAsyncKeyState(VK_F12) & 0x8000)


class InputController:
    # The bottom of the client area is the palette bar; drags must not start
    # there because the game treats it as a UI interaction.
    CANVAS_BOTTOM_FRAC = 0.85
    # A single SetCursorPos jump larger than this can be dropped by the game's
    # drag handling, so long pans are split into more steps.
    MAX_PAN_STEP_PX = 60

    def __init__(self, window_rect, palette_positions: dict = None):
        """window_rect: (left, top, width, height) of the game client area in screen coordinates."""
        self.left, self.top, self.width, self.height = window_rect
        self.palette_positions = dict(palette_positions or {})

    def _check_abort(self):
        if abort_requested():
            raise RuntimeError("Bot aborted by user (Escape or F12)")

    def _to_screen(self, x, y):
        return self.left + x, self.top + y

    def click(self, x, y, duration=0.01):
        """Click at client-relative (x, y) using direct mouse_event for speed."""
        self._check_abort()
        sx, sy = self._to_screen(x, y)
        ctypes.windll.user32.SetCursorPos(sx, sy)
        ctypes.windll.user32.mouse_event(MOUSE_LEFTDOWN, 0, 0, 0, 0)
        if duration:
            time.sleep(duration)
        ctypes.windll.user32.mouse_event(MOUSE_LEFTUP, 0, 0, 0, 0)

    def key(self, name: str, duration=0.05):
        """Press a named key."""
        self._check_abort()
        pydirectinput.keyDown(name)
        time.sleep(duration)
        pydirectinput.keyUp(name)
        time.sleep(0.05)

    def type_digit(self, digit: int):
        """Select a color by typing the digit 0-99."""
        s = str(digit)
        for ch in s:
            self.key(ch)

    def set_palette_positions(self, positions: dict):
        """positions: {color_id: (client_x, client_y)}"""
        self.palette_positions = dict(positions or {})

    def select_color(self, color_id: int):
        """Click the palette button for the given color id (1-indexed)."""
        pos = self.palette_positions.get(color_id)
        if pos:
            self.click(pos[0], pos[1], duration=0.03)

    def select_color_by_key(self, color_id: int):
        """Select a color by number using direct keybd_event for speed."""
        self._check_abort()
        if not isinstance(color_id, (int, np.integer)) or color_id < 1:
            raise ValueError(f"Invalid colour id: {color_id!r}")
        color_id = int(color_id)
        s = str(color_id)
        if color_id < 10:
            vk = _VK_DIGITS[s]
            ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.02)
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)
        else:
            for ch in s:
                vk = _VK_DIGITS[ch]
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.02)
                ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.01)
            time.sleep(0.05)

    def press_key(self, name: str):
        """Press named keys: up/down/left/right/q/e or a digit."""
        self.key(name)

    def pan(self, dx: int, dy: int, steps: int = 8):
        """Drag the canvas by (dx, dy) client pixels using the right mouse button.

        The game pans by the raw mouse delta while the right button is held, so
        this moves the artwork by exactly the requested number of pixels.
        """
        self._check_abort()
        dx, dy = int(dx), int(dy)
        if dx == 0 and dy == 0:
            return
        # Start from the middle of the playable area so that neither the start
        # nor the end of the drag leaves the canvas: releasing the button outside
        # the client area aborts the pan and loses the whole movement.
        bottom = int(self.height * self.CANVAS_BOTTOM_FRAC)
        start_x = self._clamp_drag(self.width // 2 - dx // 2, dx, 10, self.width - 10)
        start_y = self._clamp_drag(int(self.height * 0.45) - dy // 2, dy, 10, bottom)
        # Keep individual cursor jumps small enough for the game to follow.
        steps = max(steps, -(-max(abs(dx), abs(dy)) // self.MAX_PAN_STEP_PX))
        sx, sy = self._to_screen(start_x, start_y)
        ctypes.windll.user32.SetCursorPos(sx, sy)
        time.sleep(0.02)
        ctypes.windll.user32.mouse_event(MOUSE_RIGHTDOWN, 0, 0, 0, 0)
        try:
            for i in range(1, steps + 1):
                ix = sx + int(round(dx * i / steps))
                iy = sy + int(round(dy * i / steps))
                ctypes.windll.user32.SetCursorPos(ix, iy)
                time.sleep(0.005)
        finally:
            ctypes.windll.user32.mouse_event(MOUSE_RIGHTUP, 0, 0, 0, 0)
        time.sleep(0.03)

    @staticmethod
    def _clamp_drag(start: int, delta: int, low: int, high: int) -> int:
        """Clamp a drag start so both start and start+delta stay within [low, high]."""
        if high < low:
            return low
        if abs(delta) > high - low:
            # Longer than the safe area; begin at the edge with the most room.
            return low if delta > 0 else high
        if delta >= 0:
            return max(low, min(start, high - delta))
        return min(high, max(start, low - delta))

    def zoom(self, ticks: int):
        """Zoom the level camera. Positive ticks zoom in, negative zoom out."""
        self._check_abort()
        sx, sy = self._to_screen(self.width // 2, int(self.height * 0.4))
        ctypes.windll.user32.SetCursorPos(sx, sy)
        time.sleep(0.02)
        for _ in range(abs(ticks)):
            ctypes.windll.user32.mouse_event(0x0800, 0, 0, 120 if ticks > 0 else -120, 0)
            time.sleep(0.02)
        time.sleep(0.1)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import config
    from process.grid_reader import GridReader, MemoryReader
    from process.window_manager import WindowManager
    from process.vision import Vision

    r = MemoryReader(process_name=config.PROCESS_EXE)
    gr = GridReader(r)
    info = gr.read_grids()
    print("main sample", info["main"][3][3], "saved sample", info["saved"][3][3])
    window = WindowManager()
    window.update_rect()
    ctrl = InputController(window.client_rect())
    # click center of window to focus
    ctrl.click(window.width // 2, window.height // 2)
    # select color 2 and click a known uncolored cell mapped by vision
    vis = Vision(window.client_rect())
    mapping, dx, dy = vis.build_grid_mapping(info["saved"], info["main"])
    for (x, y), (cx, cy) in mapping.items():
        if main := info["main"][y][x]:
            print(f"Trying cell ({x},{y}) color {main} at ({cx},{cy})")
            ctrl.type_digit(main)
            time.sleep(0.1)
            ctrl.click(cx, cy)
            time.sleep(0.3)
            info2 = gr.read_grids()
            if info2["saved"][y][x] == main:
                print("  OK")
                break
            else:
                print("  FAIL saved", info2["saved"][y][x])
            break
    else:
        print("No mapping")
