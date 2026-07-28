"""Diagnose the CrossLevelStorage lookup for the level currently open in the game.

Usage:
    python scripts/diag_memory.py                 # identify whatever level is loaded
    python scripts/diag_memory.py "Book 1" 2      # verify a specific expected level
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from process.memory_reader import MemoryReader
from process.grid_reader import GridReader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book", nargs="?", help="Book main-menu title, e.g. 'Book 1'")
    parser.add_argument("level", nargs="?", type=int, help="Level index (0-based)")
    args = parser.parse_args()

    with open(Path(__file__).parent.parent / "data" / "levels.json") as f:
        books = json.load(f)

    reader = MemoryReader(process_name="ColoringPixels.exe")
    grid = GridReader(reader)

    if args.book is None:
        print("No book given; scanning for any book/level currently loaded...")
        for book_key, info in books.items():
            for idx, level in enumerate(info.get("levels") or []):
                base = grid.find_by_indices(idx, info.get("book_index", 0), level["x"], level["y"])
                if base:
                    print(f"Loaded: {info['main_menu_title']} / {level['display_name']} "
                          f"(index {idx}, {level['x']}x{level['y']}) @ 0x{base:08X}")
                    return
        print("No matching CrossLevelStorage found.")
        return

    title_to_key = {b["main_menu_title"]: k for k, b in books.items()}
    book_key = title_to_key[args.book]
    info = books[book_key]
    level = info["levels"][args.level]
    book_index = info.get("book_index", 0)

    print(f"Expecting {book_key}/{level['save_file']} index={args.level} "
          f"book_index={book_index} grid={level['x']}x{level['y']}")
    t0 = time.time()
    base = grid.find_by_indices(args.level, book_index, level["x"], level["y"])
    print(f"Scan took {time.time() - t0:.1f}s")
    if not base:
        print("NOT FOUND")
        return
    print(f"base            = 0x{base:08X}")
    print(f"loadLevel       = {grid.read_load_level(base)!r}")
    print(f"folderName      = {grid.read_folder_name(base)!r}")
    print(f"levelIndex      = {grid.read_level_index(base)}")
    print(f"bookIndex       = {grid.read_book_index(base)}")
    grids = grid.read_grids(base=base)
    print(f"grid            = {grids['x_max']}x{grids['y_max']}")
    uncolored = sum(1 for row in grids["saved"] for v in row if v == -1)
    print(f"uncolored cells = {uncolored}")


if __name__ == "__main__":
    main()
