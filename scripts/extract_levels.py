import sys
from pathlib import Path
import json
import struct

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GAME_DIR

import UnityPy

assets_dir = GAME_DIR / "ColoringPixels_Data"

class BinaryReader:
    def __init__(self, data: bytes):
        self.data = data
        self.off = 0

    def align(self, n=4):
        pad = (n - self.off % n) % n
        self.off += pad

    def read_int(self):
        v = struct.unpack("<i", self.data[self.off:self.off+4])[0]
        self.off += 4
        return v

    def read_uint(self):
        v = struct.unpack("<I", self.data[self.off:self.off+4])[0]
        self.off += 4
        return v

    def read_short(self):
        v = struct.unpack("<H", self.data[self.off:self.off+2])[0]
        self.off += 2
        return v

    def read_float(self):
        v = struct.unpack("<f", self.data[self.off:self.off+4])[0]
        self.off += 4
        return v

    def read_bool(self):
        v = self.data[self.off]
        self.off += 4  # Unity bools are 4-byte aligned
        return v != 0

    def read_string(self):
        length = self.read_int()
        if length < 1 or length > 1024:
            self.off += length
            self.align()
            return ""
        s = self.data[self.off:self.off+length].decode("utf-8", errors="ignore")
        self.off += length
        self.align()
        return s

    def read_pptr(self):
        # file_id (4) + path_id (8)
        self.off += 12

    def read_color(self):
        self.off += 16

    def read_int_array(self):
        length = self.read_int()
        arr = [self.read_int() for _ in range(length)]
        return arr

    def read_short_array(self):
        length = self.read_int()
        arr = [self.read_short() for _ in range(length)]
        # short arrays may be 4-byte aligned
        if length % 2:
            self.off += 2
        return arr


def parse_monobehaviour_base(r):
    # PPtr m_GameObject
    r.read_pptr()
    # UInt8 m_Enabled, 4-byte aligned
    r.read_bool()
    # PPtr m_Script
    r.read_pptr()
    # String m_Name
    return r.read_string()


def parse_level_data(r):
    display_name = r.read_string()
    display_credit = r.read_string()
    save_file = r.read_string()
    r.read_pptr()  # levelSprite
    raw = r.read_short_array()
    steam_achievement = r.read_string()
    level_link = r.read_string()
    r.read_int()  # seasonalEvent enum
    return display_name, save_file, raw


def parse_bookdetails(data):
    r = BinaryReader(data)
    parse_monobehaviour_base(r)
    r.read_bool()  # visible
    book_name = r.read_string()
    book_hash = r.read_int()
    book_index = r.read_int()
    main_menu_title = r.read_string()
    r.read_int()  # steamID
    r.read_string()  # steamAchievement
    r.read_string()  # discordImageId
    levels_count = r.read_int()
    levels = []
    for _ in range(levels_count):
        levels.append(parse_level_data(r))
    return book_name, main_menu_title, book_hash, book_index, levels


def _book_type_name(value):
    if isinstance(value, str):
        return value
    names = ["None", "Free", "Bonus", "DLC", "Reward"]
    if isinstance(value, int) and 0 <= value < len(names):
        return names[value]
    return str(value)


def main():
    out = {}
    resources_path = assets_dir / "resources.assets"
    env = UnityPy.AssetsManager(str(resources_path))
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            d = obj.read_typetree(wrap=True, check_read=False)
            script = d.m_Script.read()
            class_name = getattr(script, "m_ClassName", None) or getattr(script, "m_Name", None)
        except Exception:
            continue
        if class_name != "BookDetails":
            continue
        raw = obj.get_raw_data()
        try:
            book_name, main_menu_title, book_hash, book_index, levels = parse_bookdetails(raw)
        except Exception as e:
            print(f"Failed parsing {obj.path_id}: {e}")
            continue
        if not book_name:
            continue
        out[book_name] = {
            "main_menu_title": main_menu_title,
            "book_hash": book_hash,
            "book_index": book_index,
            "book_type": "Free",
            "levels": []
        }
        for display, save, raw_shorts in levels:
            x = raw_shorts[0]
            y = raw_shorts[1]
            grid = raw_shorts[2:2+x*y]
            color_count = raw_shorts[2+x*y]
            color_data = raw_shorts[2+x*y+1:2+x*y+1+3*color_count]
            colors = [color_data[i:i+3] for i in range(0, 3*color_count, 3)]
            out[book_name]["levels"].append({
                "display_name": display,
                "save_file": save,
                "x": x,
                "y": y,
                "grid": grid,
                "color_count": color_count,
                "colors": colors
            })
    out_path = Path(__file__).parent.parent / "data" / "levels.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {out_path}, {len(out)} books")

if __name__ == "__main__":
    main()

