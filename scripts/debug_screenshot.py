"""Save a screenshot of the game client area for UI debugging."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import cv2

from process.navigator import Navigator


def main():
    out = Path(__file__).parent.parent / "data" / "debug_screen.png"
    nav = Navigator()
    img = nav._screenshot()
    cv2.imwrite(str(out), img)
    print(f"client rect = {nav.window.client_rect()}")
    print(f"saved {out} ({img.shape[1]}x{img.shape[0]})")
    print("sidebar buttons:", nav._detect_sidebar_buttons(img))
    print("open buttons:", nav._detect_open_buttons(img))


if __name__ == "__main__":
    main()
