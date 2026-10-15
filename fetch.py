#!/usr/bin/env python3
"""Fetch Women's Bags + Ready-to-wear from Prada HK Algolia into raw_bags.json / raw_rtw.json."""
import json, urllib.request, time

A = "OCPT799JD8"
K = "ff0caf66bf2f4d3b10b59c95711ddaf8"
INDEX = "PLP_COLOR_PRADA_Online_HK"


def query(cat, hits_per=100, page=0, ts=None):
    ts = ts or int(time.time())
    params = (
        f"facetFilters=%5B%5B%22CategoriesEnriched%3A{cat}%7Cfalse%7Cfalse%22%5D%5D"
        f"&hitsPerPage={hits_per}&page={page}&facets=%5B%22*%22%5D"
        f"&filters=OnlineStartDate%20%3C%3D%20{ts}%20AND%20OnlineEndDate%20%3E%3D%20{ts}"
    )
    body = json.dumps({"params": params}).encode()
    req = urllib.request.Request(
        f"https://{A.lower()}-dsn.algolia.net/1/indexes/{INDEX}/query",
        body,
        {
            "X-Algolia-Application-Id": A,
            "X-Algolia-API-Key": K,
            "Content-Type": "application/json",
            "Referer": "https://www.prada.com/",
            "Origin": "https://www.prada.com",
            "User-Agent": "Mozilla/5.0 Chrome/126",
        },
    )
    return json.load(urllib.request.urlopen(req))


def fetch_all(cat):
    hits, page, ts = [], 0, int(time.time())
    while True:
        d = query(cat, hits_per=100, page=page, ts=ts)
        hits.extend(d["hits"])
        if page + 1 >= d["nbPages"]:
            return {"nbHits": d["nbHits"], "facets": d.get("facets"), "hits": hits}
        page += 1


if __name__ == "__main__":
    bags = fetch_all("10062HK")
    rtw = fetch_all("10048HK")
    json.dump(bags, open("raw_bags.json", "w"), ensure_ascii=False)
    json.dump(rtw, open("raw_rtw.json", "w"), ensure_ascii=False)
    # keep raw.json as bags for backwards compatibility
    json.dump(bags, open("raw.json", "w"), ensure_ascii=False)
    print("bags", len(bags["hits"]), bags["nbHits"])
    print("rtw", len(rtw["hits"]), rtw["nbHits"])
