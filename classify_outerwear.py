#!/usr/bin/env python3
"""
Classify Women's RTW outerwear as short vs long from product packshots.

Method (documented for the catalog):
1. Download PLP packshot (light gray studio background).
2. Segment garment vs background (corner-sampled BG color + brightness).
3. Estimate shoulder row (max silhouette width in upper 45%).
4. Estimate body hem (lowest foreground in center columns; trim drawstring spikes).
5. Estimate sleeve cuff:
   - Prefer "outer column" method when hem ≈ outer silhouette bottom (cropped /
     sleeves hang at/below hem).
   - Else use sleeve protrusion outside an estimated body column (long coats
     where hem extends below cuffs and body flares).
6. body_len = hem - shoulder; sleeve_len = cuff - shoulder.
7. Decision (bias toward 短外套 unless clear long-coat signals):
   - Name cues jacket / blouson / bomber / cropped / trucker / caban / blazer /
     anorak / windbreaker → short (even when packshot body > sleeve).
   - trench / overcoat / duster / car coat → long.
   - raincoat / parka / down / puffer / quilted → long only if height >= 95 cm
     or ratio >= 1.30; otherwise short. Never treat "coat" inside "raincoat".
   - traditional "coat" (no jacket) → long (unless height < 90 and ratio < 1.15).
   - Image alone: ratio >= 1.35 → long; <= 0.92 → short; else short.
   - Vest / capelet / sleeveless → short.
   - Manual overrides in outerwear_overrides.json win last.

Writes outerwear_length_map.json: {productCode: "short"|"long"}
and outerwear_img_class.json with debug fields.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent
IMG_DIR = ROOT / "ow_imgs"
DATA = ROOT / "data.json"
RAW = ROOT / "raw_rtw.json"
MAP_OUT = ROOT / "outerwear_length_map.json"
DEBUG_OUT = ROOT / "outerwear_img_class.json"
OVERRIDES = ROOT / "outerwear_overrides.json"

GARMENT = (
    "jacket", "coat", "raincoat", "parka", "cape", "blouson", "bomber",
    "trench", "caban", "blazer", "anorak", "peacoat", "vest", "hoodie",
    "windbreaker", "overcoat", "capelet",
)


def morph_open_close(mask, open_r=2, close_r=3):
    im = Image.fromarray((mask.astype(np.uint8) * 255))
    if open_r:
        k = open_r * 2 + 1
        im = im.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
    if close_r:
        k = close_r * 2 + 1
        im = im.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))
    return np.asarray(im) > 127


def analyze(path: Path):
    im = Image.open(path).convert("RGB")
    if im.width > 600:
        im = im.resize((600, int(im.height * 600 / im.width)), Image.BILINEAR)
    arr = np.asarray(im).astype(np.float32)
    h, w = arr.shape[:2]
    corners = np.stack(
        [
            arr[2, 2], arr[2, -3], arr[-3, 2], arr[-3, -3],
            arr[10, 10], arr[10, -11], arr[-11, 10], arr[-11, -11],
        ]
    )
    bg = corners.mean(axis=0)
    dist = np.linalg.norm(arr - bg, axis=2)
    bright = arr.mean(axis=2)
    fg = (dist > 30) & (bright < float(bg.mean()) - 5)
    fg = morph_open_close(fg, 2, 3)
    if fg.sum() < 400:
        fg = morph_open_close(dist > 20, 1, 2)
    ys, xs = np.where(fg)
    if len(ys) < 200:
        return None
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    gh = y1 - y0 + 1
    gw = x1 - x0 + 1
    width_at = np.zeros(h)
    for y in range(y0, y1 + 1):
        xs_row = np.where(fg[y])[0]
        if len(xs_row):
            width_at[y] = xs_row[-1] - xs_row[0] + 1
    s0, s1 = y0, y0 + max(int(gh * 0.45), 15)
    band = width_at[s0:s1]
    shoulder_y = s0 + int(np.argmax(band))
    shoulder_w = float(width_at[shoulder_y])
    cx = (x0 + x1) // 2
    half = max(int(gw * 0.12), 6)
    cys = np.where(fg[:, max(0, cx - half) : cx + half + 1].any(axis=1))[0]
    hem_y = int(cys.max()) if len(cys) else y1
    mid_w = (
        float(np.median(width_at[shoulder_y : min(shoulder_y + max(gh // 3, 5), hem_y)]))
        if hem_y > shoulder_y
        else shoulder_w
    )
    while hem_y > shoulder_y + 10 and width_at[hem_y] < max(mid_w * 0.15, 8):
        hem_y -= 1

    mid_y = shoulder_y + max((hem_y - shoulder_y) // 2, 1)
    lower_widths = width_at[mid_y : hem_y + 1]
    lower_widths = lower_widths[lower_widths > 0]
    body_w = float(np.percentile(lower_widths, 40)) if len(lower_widths) else shoulder_w * 0.55
    cropped_like = body_w > shoulder_w * 0.85
    if cropped_like:
        body_w = shoulder_w * 0.55
    body_half = body_w / 2.0
    body_l = int(cx - body_half)
    body_r = int(cx + body_half)
    sleeve_l = fg.copy()
    sleeve_l[:, body_l:] = False
    sleeve_r = fg.copy()
    sleeve_r[:, : body_r + 1] = False
    sl_ys = np.where(sleeve_l.any(axis=1))[0]
    sr_ys = np.where(sleeve_r.any(axis=1))[0]
    sl_ys = sl_ys[(sl_ys >= shoulder_y) & (sl_ys <= hem_y + 5)]
    sr_ys = sr_ys[(sr_ys >= shoulder_y) & (sr_ys <= hem_y + 5)]
    cuff_l = int(sl_ys.max()) if len(sl_ys) else shoulder_y
    cuff_r = int(sr_ys.max()) if len(sr_ys) else shoulder_y
    cuffs = [c for c in (cuff_l, cuff_r) if c > shoulder_y + 0.15 * (hem_y - shoulder_y)]
    cuff_a = int(np.median(cuffs)) if cuffs else None

    ow = max(int(gw * 0.22), 8)
    lys = np.where(fg[:, x0 : x0 + ow].any(axis=1))[0]
    rys = np.where(fg[:, max(0, x1 - ow + 1) : x1 + 1].any(axis=1))[0]
    cuff_b = int(
        ((lys.max() if len(lys) else hem_y) + (rys.max() if len(rys) else hem_y)) / 2
    )

    if cropped_like or hem_y <= cuff_b + max(int(0.02 * gh), 4):
        cuff_y = cuff_b
        method = "outer"
    else:
        cuff_y = cuff_a if cuff_a is not None else cuff_b
        method = "protrusion"

    body_len = max(hem_y - shoulder_y, 1)
    sleeve_len = max(cuff_y - shoulder_y, 1)
    ratio = body_len / float(sleeve_len)
    return {
        "ratio": round(ratio, 3),
        "body": body_len,
        "sleeve": sleeve_len,
        "hem": hem_y,
        "cuff": cuff_y,
        "shoulder": shoulder_y,
        "method": method,
        "cropped_like": cropped_like,
    }


def decide(name, height_cm, img):
    """Bias toward short unless clear long-coat name or strong long silhouette.

    Rules (user batch reclass 2026-10-15):
    - Prefer SHORT for jacket/blouson/bomber/cropped/trucker/caban/blazer/
      anorak/windbreaker — even if packshot body ≥ sleeve.
    - LONG only for trench/overcoat/traditional coat, or raincoat/parka/down
      that is clearly long (height ~≥95 cm or ratio ≥ ~1.30 / ≥1.35).
    - Do NOT treat substring "coat" inside "raincoat" as long by itself.
    - Down/puffer/quilted follow rain/parka (short unless clearly long).
    """
    n = (name or "").lower()
    ratio = img["ratio"] if img else None
    if any(w in n for w in ("vest", "capelet", "sleeveless", "gilet")):
        return "short", "sleeveless"
    if any(
        w in n
        for w in (
            "cropped", "crop ", "bomber", "blouson", "trucker", "bolero",
            "anorak", "windbreaker", "hoodie",
        )
    ):
        return "short", "name_short"
    # Jacket-family names are short even when packshot body > sleeve.
    if "jacket" in n or "caban" in n or "blazer" in n:
        return "short", "name_jacket"
    if any(w in n for w in ("trench", "overcoat", "duster", "car coat", "carcoat")):
        return "long", "name_long"
    # raincoat / parka / down-puffer: short unless clearly long silhouette.
    # "raincoat" contains "coat" — must come before generic coat.
    is_soft_long_candidate = (
        ("raincoat" in n)
        or ("parka" in n and "crop" not in n)
        or any(w in n for w in ("down", "puffer", "quilted", "quilt "))
    )
    if is_soft_long_candidate:
        if height_cm is not None and height_cm >= 95:
            return "long", "soft_tall"
        if ratio is not None and ratio >= 1.30:
            return "long", "soft_img_long"
        return "short", "soft_default_short"
    is_coat = (
        ("coat" in n)
        and ("jacket" not in n)
        and ("petticoat" not in n)
        and ("raincoat" not in n)
    )
    if is_coat:
        # Traditional coat name → long, but modest packshot height can stay short
        # when silhouette is clearly jacket-like (ratio low + height short).
        if height_cm is not None and height_cm < 90 and ratio is not None and ratio < 1.15:
            return "short", "coat_short_sil"
        return "long", "coat_name"
    if img and ratio is not None:
        if ratio >= 1.35:
            return "long", "img_long"
        if ratio <= 0.92:
            return "short", "img_short"
        if height_cm is not None and height_cm >= 100:
            return "long", "height_long"
        return "short", "near_eq_short"
    if height_cm is not None and height_cm >= 100:
        return "long", "noimg_h"
    return "short", "noimg_default"


def candidate_products(products):
    """Include remapped short/long_outerwear so re-runs after build still work."""
    out = []
    for p in products:
        if p.get("department") != "rtw":
            continue
        subs = set(p.get("subcats") or [])
        name = (p.get("name_en") or "").lower()
        if p.get("outerwear_length") in ("short", "long"):
            out.append(p)
        elif subs & {"outerwear", "jackets", "short_outerwear", "long_outerwear"}:
            out.append(p)
        elif "leather_clothing" in subs and any(w in name for w in GARMENT):
            out.append(p)
    return out


def main():
    data = json.load(open(DATA))
    products = data["products"]
    cands = candidate_products(products)
    final = {}
    for p in cands:
        path = IMG_DIR / f"{p['code']}.jpg"
        img = analyze(path) if path.exists() else None
        lab, why = decide(p.get("name_en"), p.get("height_cm"), img)
        final[p["code"]] = {
            "label": lab,
            "refine": why,
            "ratio": img["ratio"] if img else None,
            "method": img["method"] if img else None,
            "body": img["body"] if img else None,
            "sleeve": img["sleeve"] if img else None,
            "height_cm": p.get("height_cm"),
            "name": p.get("name_en"),
        }
    # Manual overrides (user corrections) win over image/name heuristics.
    ov = {}
    if OVERRIDES.exists():
        raw = json.load(open(OVERRIDES))
        ov = {k: v for k, v in raw.items() if not str(k).startswith("_") and v in ("short", "long")}
    for code, lab in ov.items():
        if code in final:
            final[code]["label"] = lab
            final[code]["refine"] = "manual_override"
        else:
            final[code] = {
                "label": lab,
                "refine": "manual_override",
                "ratio": None,
                "method": None,
                "body": None,
                "sleeve": None,
                "height_cm": None,
                "name": None,
            }
    simple = {c: v["label"] for c, v in final.items()}
    json.dump(simple, open(MAP_OUT, "w"), ensure_ascii=False, indent=2)
    json.dump(final, open(DEBUG_OUT, "w"), ensure_ascii=False, indent=2)
    print("candidates", len(cands))
    print("overrides", len(ov), sorted(ov))
    print("labels", Counter(simple.values()))
    print("why", Counter(v["refine"] for v in final.values()))
    print("wrote", MAP_OUT.name, DEBUG_OUT.name)


if __name__ == "__main__":
    main()
