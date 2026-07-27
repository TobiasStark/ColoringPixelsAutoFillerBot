import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from process.navigator import Navigator
from process.solver import Solver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-book", help="Resume from this book main-menu title")
    parser.add_argument("--start-level", type=int, default=0, help="Resume from this level index in the start book")
    parser.add_argument("--all-books", action="store_true", help="Also attempt DLC/reward books")
    args = parser.parse_args()

    levels_path = Path(__file__).parent.parent / "data" / "levels.json"
    with open(levels_path) as f:
        books = json.load(f)

    nav = Navigator()
    nav.focus()
    nav.return_to_menu()

    started = args.start_book is None
    for book_key, book_info in books.items():
        book_title = book_info["main_menu_title"]
        if not started:
            if book_title != args.start_book:
                continue
            started = True
        levels = book_info.get("levels") or []
        if not levels:
            continue
        if not args.all_books and str(book_info.get("book_type", "Free")) not in ("Free", "Bonus"):
            print(f"\n=== Skipping non-free book: {book_title} ===")
            continue
        print(f"\n=== Book: {book_title} ===")
        first_index = args.start_level if book_title == args.start_book else 0
        for level_index, level in enumerate(levels):
            if level_index < first_index:
                continue
            name = level["display_name"]
            print(f"\n[{level_index + 1}/{len(levels)}] {name}")
            try:
                base = nav.goto_level(book_title, level_index)
            except Exception as e:
                print(f"  Navigation failed: {e}")
                nav.return_to_menu()
                continue
            solver = Solver(book_name=book_key, save_file=level["save_file"], base=base)
            try:
                if solver.solve():
                    print(f"  Completed {name}")
                else:
                    print(f"  Could not complete {name}, skipping")
            except Exception as e:
                print(f"  Solver error: {e}")
            time.sleep(0.5)
            nav.return_to_menu()
            time.sleep(0.5)


if __name__ == "__main__":
    main()
