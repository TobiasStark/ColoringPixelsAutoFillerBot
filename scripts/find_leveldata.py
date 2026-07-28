import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import UnityPy

env = UnityPy.AssetsManager(str(config.GAME_DIR / "ColoringPixels_Data"))
level_objs = []
for obj in env.objects:
    if obj.type.name == "MonoBehaviour":
        try:
            d = obj.read_typetree(wrap=True, check_read=False)
            if d.m_Script:
                s = d.m_Script.read()
                class_name = getattr(s, "m_ClassName", None) or getattr(s, "m_Name", None)
            else:
                class_name = None
            if class_name == "LevelData":
                level_objs.append((d.m_Name, obj.path_id, obj.assets_file.name, obj))
        except Exception as e:
            pass

print(f"Found LevelData objects: {len(level_objs)}")
for name, pid, fname, obj in level_objs[:20]:
    print(f"  {name!r} path_id={pid} file={fname}")
