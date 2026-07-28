"""Locate and manage the game window."""
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

SW_RESTORE = 9


class WindowManager:
    def __init__(self, title=None):
        self.title = title or config.WINDOW_TITLE
        self.hwnd = 0
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0

    def find(self):
        user32 = ctypes.windll.user32
        FindWindow = user32.FindWindowW
        FindWindow.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        FindWindow.restype = wintypes.HWND
        self.hwnd = FindWindow(None, self.title) or self._find_by_substring()
        return bool(self.hwnd)

    def _find_by_substring(self):
        """Fallback for title variants such as "Coloring Pixels".

        FindWindowW only matches the exact caption, which breaks whenever the
        game (or a game update) spells its window title differently.
        """
        user32 = ctypes.windll.user32
        wanted = self.title.replace(" ", "").lower()
        match = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if wanted in buf.value.replace(" ", "").lower() and user32.IsWindowVisible(hwnd):
                    match.append(hwnd)
                    return False
            return True

        user32.EnumWindows(callback, 0)
        return match[0] if match else 0

    def update_rect(self):
        if not self.hwnd:
            self.find()
        if not self.hwnd:
            raise RuntimeError("Game window not found")
        cr = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(self.hwnd, ctypes.byref(cr))
        pt = wintypes.POINT(cr.left, cr.top)
        ctypes.windll.user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        self.left, self.top = pt.x, pt.y
        self.width, self.height = cr.right, cr.bottom
        return (self.left, self.top, self.width, self.height)

    def focus(self, timeout=1.5):
        """Bring the game to the foreground, restoring it if it was minimised.

        Returns True once the window really is in the foreground; input sent to a
        background window is silently swallowed by the game.
        """
        if not self.hwnd:
            self.find()
        if not self.hwnd:
            return False
        user32 = ctypes.windll.user32
        # Window handles do not fit into the default c_int return type.
        user32.GetForegroundWindow.restype = wintypes.HWND
        if user32.IsIconic(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_RESTORE)
        user32.SetForegroundWindow(self.hwnd)
        end = time.time() + timeout
        while time.time() < end:
            if user32.GetForegroundWindow() == self.hwnd:
                return True
            time.sleep(0.05)
        return user32.GetForegroundWindow() == self.hwnd

    def client_rect(self):
        return (self.left, self.top, self.width, self.height)
