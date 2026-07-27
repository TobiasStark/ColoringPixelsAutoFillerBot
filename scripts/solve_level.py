import argparse
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
from process.navigator import Navigator
from process.solver import Solver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book", help="Book main-menu title, e.g. 'Book 1'")
    parser.add_argument("level", type=int, help="Level index (0-based) inside the book")
    parser.add_argument("--no-nav", action="store_true", help="Skip menu navigation; level must already be loaded")
    parser.add_argument("--nav-only", action="store_true", help="Only navigate to the level, do not solve it")
    args = parser.parse_args()

    levels_path = Path(__file__).parent.parent / "data" / "levels.json"
    with open(levels_path) as f:
        levels_data = json.load(f)

    base = None
    if not args.no_nav:
        nav = Navigator()
        nav.focus()
        nav.return_to_menu()
        base = nav.goto_level(args.book, args.level)
        if args.nav_only:
            print(f"Navigation OK, CrossLevelStorage @ 0x{base:08X}")
            return

    # identify the target book key and save file for the Solver
    title_to_key = {b["main_menu_title"]: key for key, b in levels_data.items()}
    book_key = title_to_key[args.book]
    level = levels_data[book_key]["levels"][args.level]
    solver = Solver(book_name=book_key, save_file=level["save_file"], base=base)
    solver.solve()


if __name__ == "__main__":
    main()
