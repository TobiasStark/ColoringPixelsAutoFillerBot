import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import UnityPy

env = UnityPy.load(str(config.GAME_DIR / "ColoringPixels_Data"))
mbs = [o for o in env.objects if o.type.name == "MonoBehaviour"]
print(f"MonoBehaviour count: {len(mbs)}")
for mb in mbs[:50]:
    try:
        d = mb.read_typetree(wrap=True, check_read=False)
        if d.m_Script:
            s = d.m_Script.read()
            script_name = getattr(s, "m_ClassName", None) or getattr(s, "m_Name", None)
        else:
            script_name = None
        print(f"MB name={d.m_Name!r:25} script={script_name!r}")
    except Exception as e:
        print("err", type(e).__name__, e)
