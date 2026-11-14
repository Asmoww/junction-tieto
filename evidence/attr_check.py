"""Does a reference assembly define ExcludeFromCodeCoverageAttribute, and where may it be applied?"""
import sys, dnfile

TARGETS = {1: "Assembly", 2: "Module", 4: "Class", 8: "Struct", 16: "Enum", 32: "Constructor",
           64: "Method", 128: "Property", 256: "Field", 512: "Event", 1024: "Interface"}

def check(path):
    pe = dnfile.dnPE(path)
    md = pe.net.mdtables
    rows = [i for i, t in enumerate(md.TypeDef.rows, 1)
            if str(t.TypeName) == "ExcludeFromCodeCoverageAttribute"]
    if not rows:
        return f"{path}: NOT DEFINED"
    # Find the [AttributeUsage] custom attribute on that TypeDef and decode its AttributeTargets blob.
    for ca in md.CustomAttribute.rows:
        if ca.Parent.table.name == "TypeDef" and ca.Parent.row_index == rows[0]:
            blob = bytes(ca.Value.value if hasattr(ca.Value, "value") else ca.Value)
            if len(blob) >= 6 and blob[:2] == b"\x01\x00":
                v = int.from_bytes(blob[2:6], "little")
                names = [n for b, n in TARGETS.items() if v & b]
                return f"{path}: DEFINED, AttributeTargets={v} ({', '.join(names)})"
    return f"{path}: DEFINED (usage not decoded)"

for p in sys.argv[1:]:
    print(check(p))
