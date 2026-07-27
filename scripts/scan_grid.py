import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from process.memory_reader import MemoryReader

def read_array(reader, addr, expected_length=None):
    """Try to read a Mono int[,] array at addr. Return (dims, data) or None."""
    if addr == 0:
        return None
    try:
        # attempt a few header layouts; first 32 bytes
        header = reader.read_bytes(addr, 64)
    except Exception:
        return None
    # Heuristic: look for max_length and rank/element_size in first 32 bytes
    # We expect rank=2, element_size=4, max_length=169 (or dim1*dim2)
    for off in range(0, 24, 4):
        ml = int.from_bytes(header[off:off+4], "little", signed=False)
        if ml and ml < 10000:
            # rank/element_size likely 4 bytes later? Try off+4..off+8
            rank = int.from_bytes(header[off+4:off+6], "little", signed=False)
            es = int.from_bytes(header[off+6:off+8], "little", signed=False)
            if rank == 2 and es == 4 and ml == expected_length:
                data_start = off + 8
                # if bounds pointer at off+8 is non-null, data might be after pointer? try skip 4
                bounds_ptr = int.from_bytes(header[off+8:off+12], "little", signed=False)
                if bounds_ptr == 0:
                    data_start = off + 12
                else:
                    # bounds stored elsewhere; data may start after element_size/rank+bounds pointer?
                    data_start = off + 12
                try:
                    data_bytes = reader.read_bytes(addr + data_start, ml * 4)
                    data = [int.from_bytes(data_bytes[i:i+4], "little", signed=True) for i in range(0, ml*4, 4)]
                    return ml, data
                except Exception:
                    return None
    return None

def main():
    reader = MemoryReader(process_name="ColoringPixels.exe")
    print(f"Attached to PID {reader.pid}")

    pattern2 = (13).to_bytes(4, "little", signed=True) * 2
    print("Scanning for xMax=13 yMax=13 pattern:", pattern2.hex())
    hits = reader.scan_pattern(pattern2)
    print(f"Hits: {len(hits)}")

    candidates = []
    for h in hits:
        try:
            main_ptr = reader.read_ptr(h - 8)
            saved_ptr = reader.read_ptr(h - 4)
        except Exception:
            continue
        if main_ptr == 0 or saved_ptr == 0:
            continue
        # Try read arrays
        main_arr = read_array(reader, main_ptr, 169)
        saved_arr = read_array(reader, saved_ptr, 169)
        if main_arr and saved_arr:
            ml_main, data_main = main_arr
            ml_saved, data_saved = saved_arr
            # Count distinct values to tell them apart
            set_main = set(data_main)
            set_saved = set(data_saved)
            # main should contain target colors (0,1,2,3,...). saved contains -1 and colors.
            if 0 in set_main and not (-1 in set_main and len(set_main) <= 2):
                # likely mainGridValues
                candidates.append((h, main_ptr, saved_ptr, data_main, data_saved))

    print(f"Object candidates (with main/saved arrays): {len(candidates)}")
    for idx, (h, mp, sp, dm, ds) in enumerate(candidates[:5]):
        print(f"\nCandidate at 0x{h:08X} main_ptr=0x{mp:08X} saved_ptr=0x{sp:08X}")
        print(" main values set:", sorted(set(dm)))
        print(" main first 20:", dm[:20])
        print(" saved values set:", sorted(set(ds)))
        print(" saved first 20:", ds[:20])

if __name__ == "__main__":
    main()
