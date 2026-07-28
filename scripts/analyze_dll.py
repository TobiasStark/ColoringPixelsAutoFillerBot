import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import dnfile

dll_path = Path(__file__).parent.parent / "data" / "Assembly-CSharp.dll"
print(f"Loading {dll_path}")
pe = dnfile.dnPE(str(dll_path))

md = pe.net.mdtables
td = md.TypeDef
fld = md.Field

print(f"TypeDef count: {len(td)}")
print(f"Field count: {len(fld)}")

# Dump all type names to a file for inspection
out_path = Path(__file__).parent.parent / "docs" / "all_types.txt"
with open(out_path, "w", encoding="utf-8") as f:
    for row in td:
        ns = str(row.TypeNamespace or "")
        name = str(row.TypeName or "")
        f.write(f"{ns}.{name}\n")
print(f"Wrote {out_path}")

# Search for interesting keywords
keywords = ["Grid", "Cell", "Color", "Level", "Book", "Palette", "Camera", "Manager", "Input", "Save", "Game"]
interesting = []
for row in td:
    ns = str(row.TypeNamespace or "")
    name = str(row.TypeName or "")
    full = f"{ns}.{name}"
    for kw in keywords:
        if kw.lower() in name.lower():
            interesting.append(full)
            break
print(f"Interesting types: {len(interesting)}")
for t in interesting:
    print(t)

