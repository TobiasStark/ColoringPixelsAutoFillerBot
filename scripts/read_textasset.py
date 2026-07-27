import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import UnityPy

env = UnityPy.load(str(config.GAME_DIR / "ColoringPixels_Data"))
for obj in env.objects:
    if obj.type.name == "TextAsset":
        try:
            d = obj.read_typetree(wrap=True, check_read=False)
            print("TextAsset:", d.m_Name, "size:", len(d.m_Script) if hasattr(d.m_Script,'__len__') else type(d.m_Script))
            # save first bytes
            data = bytes(d.m_Script) if d.m_Script else b""
            print(data[:200])
            (Path(__file__).parent.parent / "data" / "textasset.txt").write_bytes(data)
        except Exception as e:
            print("err", e)
