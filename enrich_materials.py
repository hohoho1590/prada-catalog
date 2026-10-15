#!/usr/bin/env python3
"""Add primary_material_category and leather_type to data.json products."""
import json
from collections import Counter

LEATHER_MARKERS = (
    "leather", "calf", "nappa", "saffiano", "vernice", "suede", "patent",
    "cuir", "vitello", "vit.", "daino", "crocodile", "nubuck", "brushed",
    "cuoio", "皮革",
)
OTHER_FABRIC = (
    "linen", "denim", "corduroy", "satin", "velvet", "silk", "canvas",
    "cotton", "raffia", "straw", "duchesse", "weave", "grass", "wicker",
)

def classify(p):
    mat = (p.get("material") or "")
    name = (p.get("name_en") or "")
    group = (p.get("material_group") or "")
    blob = f"{mat} {name} {group}".lower()
    mat_l = mat.lower().strip()

    # 1) Nylon / Re-Nylon / Vela (Prada nylon fabric) / Tessuto used as nylon
    if (
        "re-nylon" in blob
        or "re nylon" in blob
        or "nylon" in blob
        or mat_l == "vela"
        or mat_l.startswith("vela ")
        or mat_l.startswith("tessuto")  # Tessuto* at Prada is Re-Nylon fabric line
    ):
        return "nylon", None

    # 2) Non-nylon fabric → 其他 (linen, denim, satin, raffia-like, etc.)
    if any(x in blob for x in OTHER_FABRIC):
        return "other", None
    if group == "面料":
        return "other", None
    if group == "面料／皮革":
        return "other", None

    # 3) Leather
    is_leather = group in ("皮革", "進口皮革") or any(x in blob for x in LEATHER_MARKERS)
    if is_leather:
        if "vernice" in blob or "varnish" in blob or "patent" in blob:
            lt = "vernice"
        elif "saffiano" in blob:
            lt = "saffiano"
        elif "nappa" in blob:
            lt = "nappa"
        elif "suede" in blob or "nubuck" in blob:
            lt = "suede"
        else:
            lt = "other_leather"
        return "leather", lt

    # fallback
    return "other", None


def main():
    d = json.load(open("data.json"))
    cats = Counter()
    types = Counter()
    ambiguous = []
    for p in d["products"]:
        cat, lt = classify(p)
        p["primary_material_category"] = cat
        p["leather_type"] = lt
        cats[cat] += 1
        if cat == "leather":
            types[lt] += 1
        # flag ambiguous: mixed nylon+leather names still nylon; fabric+leather as other
        blob = f"{(p.get('material') or '')} {(p.get('name_en') or '')}".lower()
        if cat == "nylon" and ("leather" in blob or "saffiano" in blob or "vitello" in blob):
            ambiguous.append(("nylon+leather→nylon", p.get("material"), p["name_en"][:70]))
        if cat == "other" and "leather" in blob:
            ambiguous.append(("fabric+leather→other", p.get("material"), p["name_en"][:70]))
        if cat == "leather" and not p.get("material") and "saffiano" not in blob and "nappa" not in blob and "suede" not in blob and "nubuck" not in blob:
            # generic leather from name/group only
            pass

    json.dump(d, open("data.json", "w"), ensure_ascii=False)
    print("categories:", dict(cats))
    print("leather types:", dict(types))
    print("ambiguous count:", len(ambiguous))
    # unique ambiguous patterns
    seen = set()
    for kind, mat, name in ambiguous:
        key = (kind, mat, name)
        if key in seen:
            continue
        seen.add(key)
        print(f"  AMBIG {kind}: mat={mat!r} | {name}")
    # leftover other sample
    print("\n--- other samples ---")
    for p in d["products"]:
        if p["primary_material_category"] == "other":
            print(p.get("material"), "|", p["name_en"][:80])

if __name__ == "__main__":
    main()
