"""Locate and manage the game window."""
import ctypes
from ctypes import wintypes


class WindowManager:
    def __init__(self, title="ColoringPixels"):
        self.title = title
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
        self.hwnd = FindWindow(None, self.title)
        return self.hwnd != 0

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

    def focus(self):
        if not self.hwnd:
            self.find()
        if self.hwnd:
            ctypes.windll.user32.SetForegroundWindow(self.hwnd)

    def client_rect(self):
        return (self.left, self.top, self.width, self.height)
