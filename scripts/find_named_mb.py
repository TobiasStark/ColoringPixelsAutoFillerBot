import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import UnityPy

env = UnityPy.AssetsManager(str(config.GAME_DIR / "ColoringPixels_Data"))
named = []
for obj in env.objects:
    if obj.type.name == "MonoBehaviour":
        try:
            d = obj.read_typetree(wrap=True, check_read=False)
            if d.m_Script:
                s = d.m_Script.read()
                class_name = getattr(s, "m_ClassName", None) or getattr(s, "m_Name", None)
            else:
                class_name = None
            name = d.m_Name
            if name or class_name == "LevelData":
                named.append((name, class_name, obj.path_id, obj.assets_file.name))
        except Exception as e:
            pass

print(f"Named/LevelData MonoBehaviours: {len(named)}")
for name, class_name, pid, fname in named[:100]:
    print(f"{name!r:30} {class_name!r:25} path_id={pid} file={fname}")
