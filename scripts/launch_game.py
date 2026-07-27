import subprocess
import time
import ctypes
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

def launch_and_click_play():
    # Launch via Steam
    subprocess.Popen(["cmd", "/c", "start", "steam://rungameid/897330"], shell=True)
    print("Launched Steam game, waiting for config dialog...")
    # wait for config dialog
    timeout = 60
    start = time.time()
    hwnd = 0
    while time.time() - start < timeout:
        hwnd = ctypes.windll.user32.FindWindowW(None, "ColoringPixels Configuration")
        if hwnd:
            break
        time.sleep(0.5)
    if not hwnd:
        print("Config dialog not found")
        return
    rect = (ctypes.c_int * 4)()
    ctypes.windll.user32.GetWindowRect(hwnd, rect)
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    print(f"Config dialog at {left},{top},{right},{bottom} size {w}x{h}")
    # Play! button roughly at 73% from left, 90% from top
    px = left + int(w * 0.58)
    py = top + int(h * 0.88)
    print(f"Clicking Play at {px},{py}")
    # use SendInput
    user = ctypes.windll.user32
    # move cursor
    user.SetCursorPos(px, py)
    time.sleep(0.2)
    # mouse down/up
    user.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    time.sleep(0.05)
    user.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
    print("Clicked Play")

if __name__ == "__main__":
    launch_and_click_play()
