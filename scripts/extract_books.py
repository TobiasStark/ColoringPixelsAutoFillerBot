import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import UnityPy

env = UnityPy.AssetsManager(str(config.GAME_DIR / "ColoringPixels_Data"))

# find a BookDetails asset
book = None
for obj in env.objects:
    if obj.type.name == "MonoBehaviour":
        try:
            d = obj.read_typetree(wrap=True, check_read=False)
            if d.m_Script:
                s = d.m_Script.read()
                class_name = getattr(s, "m_ClassName", None)
                if class_name == "BookDetails" and d.m_Name == "001_Free":
                    book = d
                    book_obj = obj
                    break
        except Exception:
            pass

if not book:
    print("Book not found")
    sys.exit()

print("BookDetails fields:")
for k, v in book.__dict__.items():
    print(f"  {k}: {v}")

# try raw type tree dict
tree = book_obj.read_typetree(wrap=False)
print("\nType tree keys:", tree.keys() if isinstance(tree, dict) else "not dict")
