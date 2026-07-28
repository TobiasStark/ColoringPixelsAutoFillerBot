"""List every CrossLevelStorage-looking object in memory for a given book.

Used to distinguish the live instance from destroyed leftovers.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from process.memory_reader import MemoryReader
from process.grid_reader import GridReader, LEVEL_INDEX_OFFSET


def main():
    book_title = sys.argv[1] if len(sys.argv) > 1 else "Book 1"
    with open(Path(__file__).parent.parent / "data" / "levels.json") as f:
        books = json.load(f)
    key = {b["main_menu_title"]: k for k, b in books.items()}[book_title]
    info = books[key]
    book_index = info.get("book_index", 0)

    reader = MemoryReader(process_name="ColoringPixels.exe")
    grid = GridReader(reader)

    print(f"{book_title} (book_index={book_index})")
    for idx, level in enumerate(info["levels"]):
        hits = reader.scan_int_pattern([idx, book_index, level["x"], level["y"]])
        for hit in hits:
            base = hit - LEVEL_INDEX_OFFSET
            if not grid._is_plausible_storage(base):
                continue
            cached_ptr = reader.read_ptr(base + 8)
            print(f"  idx={idx:<3} {level['display_name']:<18} {level['x']:>3}x{level['y']:<3} "
                  f"base=0x{base:08X} m_CachedPtr=0x{cached_ptr:08X} "
                  f"{'LIVE' if cached_ptr else 'destroyed'} load={grid.read_load_level(base)!r}")


if __name__ == "__main__":
    main()
