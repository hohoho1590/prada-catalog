#!/usr/bin/env python3
"""Build unified data.json from raw_bags.json + raw_rtw.json (Women's Bags + RTW)."""
import json
import re
import collections as C
from datetime import date
from pathlib import Path

SUB_BAGS = {
    "10067HK": ("top", "手挽包"),
    "10066HK": ("shoulder", "肩背包"),
    "10065HK": ("mini", "迷你手袋"),
    "10068HK": ("tote", "托特包"),
    "10063HK": ("backpack", "背囊"),
    "10064HK": ("briefcase", "公事包"),
}

SUB_RTW = {
    "10056HK": ("outerwear", "外套"),
    "10052HK": ("jackets", "外套與大衣"),
    "10054HK": ("knitwear", "針織"),
    "10050HK": ("dresses", "連身裙"),
    "10058HK": ("shirts", "恤衫與上衣"),
    "10061HK": ("tshirts", "T恤與衛衣"),
    "10060HK": ("trousers", "長褲與短褲"),
    "10059HK": ("skirts", "半身裙"),
    "10049HK": ("denim", "牛仔"),
    "11083HK": ("leather_clothing", "皮革服裝"),
    "10057HK": ("pajamas", "睡衣與內衣"),
    "10750HK": ("underwear_beach", "內衣與沙灘裝"),
    "10610HK": ("swimwear", "泳裝"),
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

OUTERWEAR_SUBS = {"outerwear", "jackets", "leather_clothing"}
OUTERWEAR_GARMENT = (
    "jacket", "coat", "raincoat", "parka", "cape", "blouson", "bomber",
    "trench", "caban", "vest", "blazer", "anorak", "peacoat", "hoodie",
)
# Estimated women's outerwear sleeve length (cm) on the same scale as ProductHeight.
# API has body height only; ~75cm best matches named jacket vs coat on this catalog.
EST_SLEEVE_CM = 75.0
SLEEVE_TOLERANCE = 0.10  # within 10% of sleeve → short

TROUSERS_SUBS = {"trousers", "denim"}  # denim may include jeans; length only if pant-like
SKIRTS_SUBS = {"skirts"}


def dim(h):
    p = [h.get(k) for k in ("ProductWidth", "ProductHeight", "ProductLength")]
    if all(x and x.get("Value") for x in p):
        return " × ".join(f"{float(x['Value']):g}" for x in p) + " cm（闊×高×深）"
    return None


def g(h, k, lang="zh_HK"):
    v = h.get(k)
    if isinstance(v, dict):
        return v.get(lang) or v.get("en_GB") or v.get("zh_CN")
    return v


def material_display(h):
    m = h.get("Material") or {}
    if not isinstance(m, dict):
        return ""
    if m.get("en_GB"):
        return m["en_GB"]
    raw = m.get("raw") or ""
    if " - " in raw:
        return raw.split(" - ", 1)[1]
    return raw


def leather_subtype(blob):
    """Shared leather subtype from material/name blob (lowercased)."""
    if "vernice" in blob or "varnish" in blob or "patent" in blob:
        return "vernice"
    if "saffiano" in blob:
        return "saffiano"
    if "nappa" in blob:
        return "nappa"
    if (
        "suede" in blob
        or "nubuck" in blob
        or "nabuk" in blob
        or "scamosciato" in blob
    ):
        return "suede"
    return "other_leather"


def classify_bags(material, name_en, material_group, raw=""):
    """Bags: 皮革 / 尼龍 / 其他 (+ leather subtypes)."""
    mat = material or ""
    name = name_en or ""
    group = (material_group or "").strip()
    blob = f"{mat} {name} {group} {raw}".lower()
    mat_l = mat.lower().strip()
    group_l = group.lower()

    if (
        "re-nylon" in blob
        or "re nylon" in blob
        or "nylon" in blob
        or group_l == "nylon"
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
    if group_l in ("cotton", "wool", "cashmere", "silk", "viscose", "linen/natural", "linen"):
        return "other", None
    if group in ("棉", "羊絨", "羊毛", "絲", "絲綢", "亞麻", "粘膠纖維", "人絲"):
        return "other", None

    is_leather = (
        group in ("皮革", "進口皮革")
        or group_l in ("leather", "sheepskin")
        or any(x in blob for x in LEATHER_MARKERS)
    )
    if is_leather:
        return "leather", leather_subtype(blob)

    return "other", None



def classify_rtw(material, name_en, material_group, raw=""):
    """
    RTW five categories based on actual MaterialGroup distribution:
      leather        皮革（含綿羊皮）
      wool_cashmere  羊毛／羊絨
      nylon          尼龍
      cotton_linen   棉／麻（含牛仔）
      silk_other     絲／其他（絲、人造絲等）
    Leather subtypes only set when category is leather (nappa/suede/…).
    """
    mat = material or ""
    name = name_en or ""
    group = (material_group or "").strip()
    blob = f"{mat} {name} {group} {raw}".lower()
    group_l = group.lower()

    # Prefer MaterialGroup when present (cleanest signal on RTW)
    if group in ("皮革", "綿羊皮") or group_l in ("leather", "sheepskin"):
        return "leather", leather_subtype(blob)
    if group in ("羊毛", "羊絨") or group_l in ("wool", "cashmere"):
        return "wool_cashmere", None
    if group == "尼龍" or group_l == "nylon":
        return "nylon", None
    if group in ("棉", "亞麻布／天然物料", "亞麻") or group_l in ("cotton", "linen/natural", "linen"):
        return "cotton_linen", None
    if group in ("絲", "絲綢", "人造絲", "粘膠纖維") or group_l in ("silk", "viscose"):
        return "silk_other", None

    # Fallback on material / name text
    if any(x in blob for x in ("re-nylon", "re nylon", "nylon", "vela", "tessuto")):
        return "nylon", None
    if any(x in blob for x in LEATHER_MARKERS) or "shearling" in blob or "montone" in blob:
        return "leather", leather_subtype(blob)
    if any(x in blob for x in ("cashmere", "wool", "mohair", "alpaca", "camel", "tweed", "cashwool", "lana", "re-wool")):
        return "wool_cashmere", None
    if any(x in blob for x in ("cotton", "denim", "linen", "chino", "canvas", "poplin", "popeline", "piquet", "chambray", "gabardine")):
        # gabardine can be nylon-tech; if nylon not caught above, cotton default OK for cotton gabardine
        if "nylon" in blob:
            return "nylon", None
        return "cotton_linen", None
    if any(x in blob for x in ("silk", "satin", "duchesse", "faille", "organza", "viscose", "velvet", "velluto", "raso")):
        return "silk_other", None

    return "silk_other", None


def product_height_cm(h):
    ph = h.get("ProductHeight") or {}
    try:
        return float(ph.get("Value"))
    except (TypeError, ValueError):
        return None


def classify_sleeve(name_en):
    """sleeveless | short | long | unknown — from English product name."""
    n = (name_en or "").lower()
    if any(
        w in n
        for w in (
            "sleeveless",
            "sleeve-less",
            "without sleeves",
            "no sleeve",
        )
    ):
        return "sleeveless"
    if any(w in n for w in ("tank top", "tank ", " tank", "camisole", "halter", "gilet")):
        return "sleeveless"
    # vest as garment (not investment) — outerwear/knit vest
    if re.search(r"\bvest\b", n):
        return "sleeveless"
    if any(
        w in n
        for w in (
            "short-sleeve",
            "short sleeve",
            "shortsleeve",
            "short sleeved",
            "cap sleeve",
            "cap-sleeve",
        )
    ):
        return "short"
    if any(
        w in n
        for w in (
            "three-quarter sleeve",
            "3/4 sleeve",
            "¾ sleeve",
        )
    ):
        return "short"
    if any(
        w in n
        for w in (
            "long-sleeve",
            "long sleeve",
            "longsleeve",
            "long sleeved",
        )
    ):
        return "long"
    return "unknown"


def classify_outerwear_length(name_en, subcats, height_cm=None):
    """
    long / short / unknown for outerwear-like garments; None if not outerwear.
    Rule: body longer than sleeve (>10%) → long; body ≈ sleeve (within 10%) or shorter → short.
    Prefer ProductHeight vs estimated sleeve; else name heuristics.
    """
    subs = set(subcats or [])
    if not (subs & OUTERWEAR_SUBS):
        return None
    name = (name_en or "").lower()
    if not any(w in name for w in OUTERWEAR_GARMENT):
        # leather skirts / shirts tagged under leather_clothing
        return None

    # Dimension rule (body vs estimated sleeve)
    if height_cm is not None and height_cm > 0:
        # Sleeveless outerwear (vests): treat as short — no sleeve to compare
        if re.search(r"\bvest\b", name) or "capelet" in name:
            return "short"
        sleeve = EST_SLEEVE_CM
        if height_cm > sleeve * (1.0 + SLEEVE_TOLERANCE):
            return "long"
        return "short"

    # Name heuristics fallback
    if "cropped" in name or "crop " in name or name.startswith("crop"):
        return "short"
    if re.search(r"\bvest\b", name) or "capelet" in name:
        return "short"
    if any(w in name for w in ("bomber", "blouson", "trucker", "blazer")):
        return "short"
    if any(w in name for w in ("raincoat", "trench", "overcoat", "parka", "duster")):
        return "long"
    if re.search(r"\bcoat\b", name) and "jacket" not in name:
        return "long"
    if re.search(r"\bcape\b", name):
        return "long"
    if "caban" in name:
        return "short"
    if "jacket" in name:
        return "short"
    return "unknown"


def classify_bottom_length(name_en, subcats, height_cm=None, kind="trousers"):
    """short / long for trousers or skirts; None if not applicable."""
    subs = set(subcats or [])
    name = (name_en or "").lower()

    if kind == "trousers":
        if "trousers" not in subs and "denim" not in subs:
            return None
        # Only pant-like denim; skip jackets/shirts wrongly tagged
        if "denim" in subs and "trousers" not in subs:
            if not any(w in name for w in ("jean", "pant", "trouser", "short", "bermuda", "chino", "jogger")):
                return None
        # Name first (Bermudas mis-tagged with long height exist)
        if any(w in name for w in ("short", "shorts", "bermuda", "bermudas", "hot pant")):
            return "short"
        if any(w in name for w in ("pant", "trouser", "jogger", "legging", "chino", "jean")):
            return "long"
        if height_cm is not None:
            return "short" if height_cm < 80 else "long"
        return "unknown"

    if kind == "skirts":
        if "skirts" not in subs:
            return None
        if any(w in name for w in ("miniskirt", "mini-skirt", "mini skirt", "mini-skirt")):
            return "short"
        if "mini" in name and "skirt" in name:
            return "short"
        if any(w in name for w in ("midi", "maxi", "full skirt", "full-skirt")):
            return "long"
        if height_cm is not None:
            # minis ~32–45; knee/midi ~60–85; long midi ~120
            return "short" if height_cm < 55 else "long"
        return "unknown"

    return None


def build_product(h, department, sub_map, default_sub_zh):

    cats = h.get("Categories") or []
    subs = [sub_map[c] for c in sub_map if c in cats]
    col = lambda s: (s or "").split("|||")
    url_path = (h.get("UrlReconstructed") or {}).get("en_GB") or ""
    url = "https://www.prada.com/hk/en" + url_path
    m = h.get("Material") if isinstance(h.get("Material"), dict) else {}
    mat_en = (m or {}).get("en_GB") or ""
    raw = (m or {}).get("raw") or ""
    material = material_display(h)
    material_group = g(h, "MaterialGroup")
    name_en = g(h, "ProductName", "en_GB")
    raw_for_class = raw if (
        "nylon" in raw.lower() or "vela" in raw.lower() or "tessuto" in raw.lower()
    ) else ""
    height_cm = product_height_cm(h)
    sleeve = classify_sleeve(name_en)
    bottom_len = None
    if department == "bags":
        cat, lt = classify_bags(mat_en, name_en, material_group, raw_for_class)
        ow_len = None
        sleeve = None  # not applicable
    else:
        cat, lt = classify_rtw(mat_en, name_en, material_group, raw_for_class)
        subcat_ids = [s[0] for s in subs]
        ow_len = classify_outerwear_length(name_en, subcat_ids, height_cm)
        # trousers / skirts short vs long
        if set(subcat_ids) & {"trousers", "denim"}:
            bottom_len = classify_bottom_length(name_en, subcat_ids, height_cm, "trousers")
        if bottom_len is None and "skirts" in subcat_ids:
            bottom_len = classify_bottom_length(name_en, subcat_ids, height_cm, "skirts")
    imgs = h.get("Images") or {}
    plp = imgs.get("PLPBKG") or ""
    image = (plp + "/_jcr_content/renditions/cq5dam.web.hebebed.800.800.jpg") if plp else ""
    return dict(
        code=h["objectID"],
        model=(h.get("Model") or {}).get("Code") if isinstance(h.get("Model"), dict) else h.get("Model"),
        department=department,
        name_en=name_en,
        name_zh=g(h, "ProductName"),
        price=(h.get("Price") or {}).get("Value"),
        color_en=col(g(h, "Color", "en_GB") or "")[0],
        color_zh=col(g(h, "Color") or "")[0],
        color_hex=col(g(h, "Color", "en_GB") or "")[-1],
        color_group=col(g(h, "ColorGroup") or "")[0],
        color_group_en=col(g(h, "ColorGroup", "en_GB") or "")[0],
        material=material,
        material_group=material_group,
        primary_material_category=cat,
        leather_type=lt,
        outerwear_length=ow_len,
        garment_length=bottom_len,  # short/long for trousers & skirts
        sleeve_type=sleeve,  # sleeveless/short/long/unknown for RTW
        height_cm=height_cm,
        size=g(h, "BagDimension", "zh_HK"),
        dimensions=dim(h),
        subcats=[s[0] for s in subs],
        subcat_zh=[s[1] for s in subs] or [default_sub_zh],
        line=g(h, "ProductType", "en_GB"),
        other_colors=[
            o["Code"] for o in h.get("OtherColors") or []
            if isinstance(o, dict) and "Code" in o
        ],
        image=image,
        image2=imgs.get("HoverBKG"),
        url=url,
        availability=h.get("Availability"),
    )


def load_raw(name):
    p = Path(name)
    if not p.exists():
        raise SystemExit(f"missing {name}; run fetch.py first")
    return json.load(open(p))


def main():
    bags_raw = load_raw("raw_bags.json") if Path("raw_bags.json").exists() else load_raw("raw.json")
    rtw_raw = load_raw("raw_rtw.json")

    bags = [build_product(h, "bags", SUB_BAGS, "其他（小袋／吊飾等）") for h in bags_raw["hits"]]
    rtw = [build_product(h, "rtw", SUB_RTW, "其他成衣") for h in rtw_raw["hits"]]

    seen = set()
    out = []
    for p in bags + rtw:
        if p["code"] in seen:
            continue
        seen.add(p["code"])
        out.append(p)

    payload = {
        "source": {
            "bags": "https://www.prada.com/hk/en/womens/bags/c/10062HK",
            "rtw": "https://www.prada.com/hk/en/womens/ready-to-wear/c/10048HK",
            "ui": "sleeve-bottom-ow-v7",
        },
        "fetched": date.today().isoformat(),
        "count": len(out),
        "counts": {"bags": len(bags), "rtw": len(rtw)},
        "products": out,
    }
    json.dump(payload, open("data.json", "w"), ensure_ascii=False)
    print("total", len(out), "bags", len(bags), "rtw", len(rtw))
    print("bags subcats", C.Counter(s for o in bags for s in o["subcat_zh"]))
    print("rtw subcats", C.Counter(s for o in rtw for s in o["subcat_zh"]))
    print("bags material", C.Counter(o["primary_material_category"] for o in bags))
    print("rtw material", C.Counter(o["primary_material_category"] for o in rtw))
    print("bags leather", C.Counter(o["leather_type"] for o in bags if o["primary_material_category"] == "leather"))
    print(
        "rtw outerwear_length",
        C.Counter(o["outerwear_length"] for o in rtw if o["outerwear_length"] is not None),
    )
    ow = [o for o in rtw if o["outerwear_length"] is not None]
    print("outerwear classified", len(ow), C.Counter(o["outerwear_length"] for o in ow))
    print(
        "rtw sleeve_type",
        C.Counter(o["sleeve_type"] for o in rtw),
    )
    bottoms = [o for o in rtw if o.get("garment_length") is not None]
    print(
        "rtw garment_length (trousers/skirts)",
        len(bottoms),
        C.Counter(o["garment_length"] for o in bottoms),
    )
    tr = [o for o in rtw if "trousers" in o["subcats"]]
    sk = [o for o in rtw if "skirts" in o["subcats"]]
    print("trousers length", C.Counter(o.get("garment_length") for o in tr))
    print("skirts length", C.Counter(o.get("garment_length") for o in sk))
    print("missing image", sum(1 for o in out if not o["image"]))
    print("missing price", sum(1 for o in out if not o["price"]))


if __name__ == "__main__":
    main()
