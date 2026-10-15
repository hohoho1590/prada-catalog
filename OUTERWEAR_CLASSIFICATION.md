# Outerwear short vs long classification

Women's RTW **全部總類** uses top-level **短外套** / **長外套** (API categories `outerwear` + `jackets` + leather jackets/coats are remapped). No bare 外套 / 外套與大衣.

## Rule (user batch reclass 2026-10-15)

Do **not** treat packshot body length > sleeve length alone as 長外套.
Many short jackets (rain jacket, down jacket, blouson, parka) photograph with body ≥ sleeve.

Prefer:

- **短外套**: jacket / blouson / bomber / cropped / trucker / caban / blazer / anorak / windbreaker; near-equal or modest body>sleeve; raincoat / parka / down / puffer / quilted without clear long silhouette
- **長外套**: trench / overcoat / duster / car coat; traditional "coat" (no jacket) when not short silhouette; raincoat / parka / down only when height ≥ ~95 cm or body/sleeve ratio ≥ ~1.30; strong long silhouette (ratio ≥ ~1.35)

Never treat the substring `coat` inside `raincoat` as long by itself.

## Method

Script: `classify_outerwear.py` → `outerwear_length_map.json` (consumed by `build.py`).

1. Segment packshot vs light gray studio background (corner-sampled BG).
2. Shoulder ≈ max silhouette width in upper 45%.
3. Hem ≈ lowest foreground in center columns (trim drawstring spikes).
4. Cuff ≈ outer-column bottoms when cropped / sleeves at hem; else sleeve protrusion outside estimated body column (long coats).
5. `ratio = body_len / sleeve_len`.
6. Decide with **name-first short bias**, then tall height / strong ratio for long coats. Manual overrides win last.

Rebuild: run `classify_outerwear.py` (images in `ow_imgs/` if present) then `python3 build.py`.

## Manual overrides

File: `outerwear_overrides.json` — `{productCode: "short"|"long"}`.

Loaded by `build.py` (wins over `outerwear_length_map.json`) and by
`classify_outerwear.py` when rewriting the map, so rebuilds keep user
corrections (e.g. 29S427 / 292252 / 292391 / 292348 / 29X966 / 292214 packshots marked 短外套).
