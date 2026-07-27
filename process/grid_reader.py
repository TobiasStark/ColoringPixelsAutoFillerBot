"""Read current level grids from process memory."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from process.memory_reader import MemoryReader

# Mono lays out reference fields first, then value types. For CrossLevelStorage:
#   refs   : loadLevel(12) folderName(16) mainGridValues(20) savedGridValues(24)
#            colours(28) achievementID(32) discordID(36) books(40)
#            persistentDataPath(44) levelLink(48) bonus(52) complete(56)
#            key(60) iv(64)
#   values : levelIndex(68) bookIndex(72) xMax(76) yMax(80) ...
#
# UnityEngine.Object stores its native handle in m_CachedPtr at +8. Unity zeroes
# it when the object is destroyed, which is the only reliable way to tell the
# live CrossLevelStorage apart from leftovers of previous scenes that the GC has
# not collected yet.
M_CACHED_PTR_OFFSET = 8
LOAD_LEVEL_OFFSET = 12
CROSS_LEVEL_FOLDER_OFFSET = 16
MAIN_GRID_OFFSET = 20
SAVED_GRID_OFFSET = 24
PERSISTENT_PATH_OFFSET = 44
LEVEL_INDEX_OFFSET = 68
BOOK_INDEX_OFFSET = 72
X_MAX_OFFSET = 76
Y_MAX_OFFSET = 80
LAST_BOOK_HASH_OFFSET = 84


class GridReader:
    def __init__(self, reader: MemoryReader):
        self.reader = reader
        # CrossLevelStorage is DontDestroyOnLoad, so its address is stable for the
        # whole process lifetime. Cache it to avoid repeated full-memory scans.
        self._base_cache = 0

    def _find_mono_string(self, text: str) -> list:
        """Return object start addresses of MonoString objects containing text."""
        pattern = len(text).to_bytes(4, "little") + text.encode("utf-16-le")
        # require at least one null padding word following chars so we don't match substrings
        hits = self.reader.scan_pattern(pattern)
        results = []
        for h in hits:
            obj = h - 8  # length prefix is at +8 inside MonoString
            # validate length
            try:
                length = self.reader.read_int(obj + 8)
            except Exception:
                continue
            if length == len(text):
                results.append(obj)
        return results

    @staticmethod
    def _book_name_variants(book_name):
        """Return possible folder-name variants (e.g. 'Book1' -> ['Book1', 'Book 1'])."""
        if isinstance(book_name, (list, tuple)):
            names = list(book_name)
        else:
            names = [str(book_name)]
        variants = set()
        for n in names:
            variants.add(n)
            # split on digit boundaries and rejoin with spaces
            spaced = re.sub(r'(?<=\D)(?=\d)|(?<=\d)(?=\D)', ' ', n).strip()
            if spaced and spaced != n:
                variants.add(spaced)
        return list(variants)

    def _find_mono_strings(self, texts: list):
        """Find MonoString objects for multiple candidate texts."""
        results = []
        seen = set()
        for text in texts:
            for obj in self._find_mono_string(text):
                if obj not in seen:
                    seen.add(obj)
                    results.append(obj)
        return results

    def is_live(self, base: int) -> bool:
        """True if the Unity object at base has not been destroyed."""
        try:
            return self.reader.read_ptr(base + M_CACHED_PTR_OFFSET) != 0
        except Exception:
            return False

    def _is_plausible_storage(self, base: int, require_live: bool = True) -> bool:
        """Check that base looks like a live CrossLevelStorage with loaded grids."""
        if require_live and not self.is_live(base):
            return False
        try:
            x_max = self.reader.read_int(base + X_MAX_OFFSET)
            y_max = self.reader.read_int(base + Y_MAX_OFFSET)
            main_ptr = self.reader.read_ptr(base + MAIN_GRID_OFFSET)
            saved_ptr = self.reader.read_ptr(base + SAVED_GRID_OFFSET)
        except Exception:
            return False
        if x_max <= 0 or x_max > 1000 or y_max <= 0 or y_max > 1000:
            return False
        expected = x_max * y_max
        return self._is_valid_int_array(main_ptr, expected) and self._is_valid_int_array(saved_ptr, expected)

    def find_by_indices(self, level_index: int, book_index: int, x_max: int, y_max: int) -> int:
        """Locate CrossLevelStorage via its contiguous levelIndex/bookIndex/xMax/yMax block.

        This is a single 16-byte scan over writable pages, which is far faster and
        more reliable than resolving the folderName string and all its referrers.
        """
        hits = self.reader.scan_int_pattern([level_index, book_index, x_max, y_max])
        for hit in hits:
            base = hit - LEVEL_INDEX_OFFSET
            if self._is_plausible_storage(base):
                self._base_cache = base
                return base
        return 0

    def is_storage(self, base: int) -> bool:
        """Validate that base is the live CrossLevelStorage of this game."""
        if not self.is_live(base):
            return False
        try:
            path = self._read_mono_string(self.reader.read_ptr(base + PERSISTENT_PATH_OFFSET))
        except Exception:
            return False
        return "ColoringPixels" in path.replace("\\", "/")

    def find_storage(self, book_hashes) -> int:
        """Locate the live CrossLevelStorage regardless of the current scene.

        lastBookOpenHash always holds one of the game's book hashes, which makes a
        cheap single-pass anchor; persistentDataPath then confirms the object.
        """
        if self._base_cache and self.is_storage(self._base_cache):
            return self._base_cache
        hashes = list(book_hashes)
        found = self.reader.scan_int_patterns([[h] for h in hashes])
        for hits in found.values():
            for hit in hits:
                base = hit - LAST_BOOK_HASH_OFFSET
                if self.is_storage(base):
                    self._base_cache = base
                    return base
        return 0

    def read_last_book_hash(self, base: int) -> int:
        return self.reader.read_int(base + LAST_BOOK_HASH_OFFSET)

    def find_loaded_level(self, levels: list, book_index: int):
        """Return (level_index, base) of the live CrossLevelStorage for this book.

        `levels` is the book's level list from levels.json. All candidate
        signatures are searched in one pass, so the cost does not grow with the
        number of levels in the book.
        """
        signatures = [[i, book_index, lv["x"], lv["y"]] for i, lv in enumerate(levels)]
        found = self.reader.scan_int_patterns(signatures)
        for i, hits in found.items():
            for hit in hits:
                base = hit - LEVEL_INDEX_OFFSET
                if self._is_plausible_storage(base):
                    self._base_cache = base
                    return i, base
        return None, 0

    def find_cross_level_storage(self, book_name: str = "Book1", save_file: str = None) -> int:
        """Find CrossLevelStorage object base address for a given book folder name and optionally save file."""
        # The singleton never moves, so re-validate the cached address first.
        if self._base_cache and self._is_plausible_storage(self._base_cache):
            if not save_file:
                return self._base_cache
            load = self.read_load_level(self._base_cache)
            if self._save_matches(save_file, load):
                return self._base_cache
            # Right object, wrong level loaded: caller should retry, not rescan.
            return 0

        book_candidates = self._book_name_variants(book_name)
        for sobj in self._find_mono_strings(book_candidates):
            ptr_bytes = sobj.to_bytes(4, "little")
            refs = self.reader.scan_pattern(ptr_bytes)
            for ref in refs:
                base = ref - CROSS_LEVEL_FOLDER_OFFSET
                if not self._is_plausible_storage(base):
                    continue
                # Identify which string field holds the folder name; Mono may order
                # loadLevel/folderName either way depending on the build.
                try:
                    s_load = self._read_mono_string(self.reader.read_ptr(base + LOAD_LEVEL_OFFSET))
                    s_folder = self._read_mono_string(self.reader.read_ptr(base + CROSS_LEVEL_FOLDER_OFFSET))
                except Exception:
                    continue
                if s_folder in book_candidates:
                    load = s_load
                elif s_load in book_candidates:
                    load = s_folder
                else:
                    continue
                if save_file and not self._save_matches(save_file, load):
                    continue
                self._base_cache = base
                return base
        return 0

    @staticmethod
    def _save_matches(save_file: str, load_level: str) -> bool:
        if not save_file:
            return True
        save = save_file.lower()
        load = (load_level or "").lower()
        if not load:
            return False
        return save in load or load in save

    def read_level_index(self, base: int) -> int:
        return self.reader.read_int(base + LEVEL_INDEX_OFFSET)

    def read_book_index(self, base: int) -> int:
        return self.reader.read_int(base + BOOK_INDEX_OFFSET)

    def _is_valid_int_array(self, obj_addr: int, expected_len: int) -> bool:
        try:
            max_len = self.reader.read_int(obj_addr + 12)
        except Exception:
            return False
        return max_len == expected_len

    def _read_mono_string(self, ptr: int) -> str:
        """Read a MonoString object given its pointer."""
        if ptr == 0:
            return ""
        try:
            length = self.reader.read_int(ptr + 8)
            if length <= 0 or length > 1024:
                return ""
            data = self.reader.read_bytes(ptr + 12, length * 2)
            return data.decode("utf-16-le", errors="ignore")
        except Exception:
            return ""

    def read_folder_name(self, base: int) -> str:
        ptr = self.reader.read_ptr(base + CROSS_LEVEL_FOLDER_OFFSET)
        return self._read_mono_string(ptr)

    def read_load_level(self, base: int) -> str:
        ptr = self.reader.read_ptr(base + LOAD_LEVEL_OFFSET)
        return self._read_mono_string(ptr)

    def read_int_array(self, obj_addr: int, x_max: int, y_max: int):
        """Read int[,] object and return flat memory-order values."""
        data_addr = obj_addr + 16
        max_len = self.reader.read_int(obj_addr + 12)
        if max_len != x_max * y_max:
            raise ValueError(f"Array length mismatch: {max_len} vs {x_max * y_max}")
        data = self.reader.read_bytes(data_addr, max_len * 4)
        return [int.from_bytes(data[i:i+4], "little", signed=True) for i in range(0, max_len*4, 4)]

    def to_logical(self, flat: list, x_max: int, y_max: int):
        """Convert memory-order (column-major, bottom-to-top per column) to logical top-to-bottom rows."""
        grid = [[0]*x_max for _ in range(y_max)]
        for x in range(x_max):
            for y_top in range(y_max):
                mem_idx = x * y_max + (y_max - 1 - y_top)
                grid[y_top][x] = flat[mem_idx]
        return grid

    def read_grids(self, base: int = None, book_name: str = "Book1", save_file: str = None):
        if base is None:
            base = self.find_cross_level_storage(book_name, save_file)
        if base == 0:
            raise RuntimeError("Could not find CrossLevelStorage object")
        main_ptr = self.reader.read_ptr(base + MAIN_GRID_OFFSET)
        saved_ptr = self.reader.read_ptr(base + SAVED_GRID_OFFSET)
        x_max = self.reader.read_int(base + X_MAX_OFFSET)
        y_max = self.reader.read_int(base + Y_MAX_OFFSET)
        main_flat = self.read_int_array(main_ptr, x_max, y_max)
        saved_flat = self.read_int_array(saved_ptr, x_max, y_max)
        main_grid = self.to_logical(main_flat, x_max, y_max)
        saved_grid = self.to_logical(saved_flat, x_max, y_max)
        return {
            "x_max": x_max,
            "y_max": y_max,
            "main": main_grid,
            "saved": saved_grid,
            "base": base,
            "main_ptr": main_ptr,
            "saved_ptr": saved_ptr,
        }


if __name__ == "__main__":
    r = MemoryReader(process_name="ColoringPixels.exe")
    gr = GridReader(r)
    base = gr.find_cross_level_storage("Book1")
    print(f"CrossLevelStorage at 0x{base:08X}")
    info = gr.read_grids(base)
    print(f"grid {info['x_max']}x{info['y_max']}")
    for row in info["main"][:5]:
        print(row)
    print("saved sample:")
    for row in info["saved"][:5]:
        print(row)
