import json
import collections as C

d = json.load(open("raw.json"))
SUB = {
    "10067HK": ("top", "手挽包"),
    "10066HK": ("shoulder", "肩背包"),
    "10065HK": ("mini", "迷你手袋"),
    "10068HK": ("tote", "托特包"),
    "10063HK": ("backpack", "背囊"),
    "10064HK": ("briefcase", "公事包"),
}

LEATHER_MARKERS = (
    "leather", "calf", "nappa", "saffiano", "vernice", "suede", "patent",
    "cuir", "vitello", "vit.", "daino", "crocodile", "nubuck", "brushed",
    "cuoio", "皮革",
)
OTHER_FABRIC = (
    "linen", "denim", "corduroy", "satin", "velvet", "silk", "canvas",
    "cotton", "raffia", "straw", "duchesse", "weave", "grass", "wicker",
)


def dim(h):
    p = [h.get(k) for k in ("ProductWidth", "ProductHeight", "ProductLength")]
    if all(x and x.get("Value") for x in p):
        return " × ".join(f"{float(x['Value']):g}" for x in p) + " cm（闊×高×深）"
    return None


def classify(material, name_en, material_group):
    mat = material or ""
    name = name_en or ""
    group = material_group or ""
    blob = f"{mat} {name} {group}".lower()
    mat_l = mat.lower().strip()

    if (
        "re-nylon" in blob
        or "re nylon" in blob
        or "nylon" in blob
        or mat_l == "vela"
        or mat_l.startswith("vela ")
        or mat_l.startswith("tessuto")
    ):
        return "nylon", None

    if any(x in blob for x in OTHER_FABRIC):
        return "other", None
    if group == "面料":
        return "other", None
    if group == "面料／皮革":
        return "other", None

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

    return "other", None


out = []
for h in d["hits"]:
    g = lambda k, l="zh_HK": (h.get(k) or {}).get(l)
    cats = h.get("Categories") or []
    subs = [SUB[c] for c in SUB if c in cats]
    col = lambda s: (s or "").split("|||")
    url = "https://www.prada.com/hk/en" + (h["UrlReconstructed"]["en_GB"])
    material = g("Material", "en_GB")
    material_group = g("MaterialGroup")
    name_en = g("ProductName", "en_GB")
    cat, lt = classify(material, name_en, material_group)
    out.append(
        dict(
            code=h["objectID"],
            model=(h.get("Model") or {}).get("Code"),
            name_en=name_en,
            name_zh=g("ProductName"),
            price=(h.get("Price") or {}).get("Value"),
            color_en=col(g("Color", "en_GB"))[0],
            color_zh=col(g("Color"))[0],
            color_hex=col(g("Color", "en_GB"))[-1],
            color_group=col(g("ColorGroup"))[0],
            color_group_en=col(g("ColorGroup", "en_GB"))[0],
            material=material,
            material_group=material_group,
            primary_material_category=cat,
            leather_type=lt,
            size=g("BagDimension", "zh_HK"),
            dimensions=dim(h),
            subcats=[s[0] for s in subs],
            subcat_zh=[s[1] for s in subs] or ["其他（小袋／吊飾等）"],
            line=g("ProductType", "en_GB"),
            other_colors=[o["Code"] for o in h.get("OtherColors") or []],
            image=((h.get("Images") or {}).get("PLPBKG") or "")
            + "/_jcr_content/renditions/cq5dam.web.hebebed.800.800.jpg",
            image2=(h.get("Images") or {}).get("HoverBKG"),
            url=url,
            availability=h.get("Availability"),
        )
    )

json.dump(
    {
        "source": "https://www.prada.com/hk/en/womens/bags/c/10062HK",
        "fetched": "2026-10-15",
        "count": len(out),
        "products": out,
    },
    open("data.json", "w"),
    ensure_ascii=False,
)
print(len(out))
for k in ["price", "image", "material", "dimensions", "size", "line", "name_zh"]:
    print(k, sum(1 for o in out if o[k]))
print(C.Counter(s for o in out for s in o["subcat_zh"]))
print("material cats", C.Counter(o["primary_material_category"] for o in out))
print("leather types", C.Counter(o["leather_type"] for o in out if o["primary_material_category"] == "leather"))
