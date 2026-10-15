# Outerwear short vs long classification

Women's RTW **全部總類** uses top-level **短外套** / **長外套** (API categories `outerwear` + `jackets` + leather jackets/coats are remapped).

## Rule (user)

Compare garment **body length** to **sleeve length** on the product packshot:

- body longer than sleeves → **長外套**
- otherwise (including near-equal) → **短外套**

## Method

Script: `classify_outerwear.py` → `outerwear_length_map.json` (consumed by `build.py`).

1. Segment packshot vs light gray studio background (corner-sampled BG).
2. Shoulder ≈ max silhouette width in upper 45%.
3. Hem ≈ lowest foreground in center columns (trim drawstring spikes).
4. Cuff ≈ outer-column bottoms when cropped / sleeves at hem; else sleeve protrusion outside estimated body column (long coats).
5. `ratio = body_len / sleeve_len`.
6. Decide with image ratio plus name/height tie-breaks for near-equal cases (raincoats, coats, cropped/bomber/blouson → short, etc.).

Rebuild: run `classify_outerwear.py` (images in `ow_imgs/` if present) then `python3 build.py`.
