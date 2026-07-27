import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import UnityPy

env = UnityPy.load(str(config.GAME_DIR / "ColoringPixels_Data"))
scripts = {}
for obj in env.objects:
    if obj.type.name == "MonoScript":
        try:
            s = obj.read()
            name = getattr(s, "m_ClassName", None) or getattr(s, "m_Name", None)
            scripts[name] = (obj.path_id, obj.assets_file.name)
        except Exception as e:
            pass

print(f"MonoScript count: {len(scripts)}")
for k in sorted(scripts):
    print(k, scripts[k])
