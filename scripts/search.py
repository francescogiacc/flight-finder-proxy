#!/usr/bin/env python3
"""
Parallel flight search via SerpAPI.
Reads PAYLOAD and SERPAPI_KEY from env, writes results/latest.json.
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

payload = json.loads(os.environ["PAYLOAD"])
serpapi_key = os.environ["SERPAPI_KEY"]
secret = "ff2026-chianti"

if payload.get("token") != secret:
    os.makedirs("results", exist_ok=True)
    with open("results/latest.json", "w") as f:
        json.dump({"error": "Unauthorized"}, f)
    sys.exit(0)

searches = payload.get("searches", [])
if not searches:
    print("No searches in payload")
    sys.exit(1)


def fetch(s):
    key = s["arrival_id"] + "_" + s.get("return_date", s.get("outbound_date", ""))
    params = {
        "engine": "google_flights",
        "api_key": serpapi_key,
        "departure_id": "BER",
        "arrival_id": s["arrival_id"],
        "outbound_date": s["outbound_date"],
        "adults": "1",
        "stops": "0",
        "currency": "EUR",
        "hl": "it",
        "type": "1" if s.get("return_date") else "2",
    }
    if s.get("return_date"):
        params["return_date"] = s["return_date"]

    url = "https://serpapi.com/search?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        status = data.get("search_metadata", {}).get("status", "?")
        print(f"Done: {key} | status={status}")
        return key, data
    except Exception as e:
        print(f"Error: {key} | {e}")
        return key, {"error": str(e)}


results = {}
with ThreadPoolExecutor(max_workers=6) as ex:
    futures = {ex.submit(fetch, s): s for s in searches}
    for fut in as_completed(futures):
        k, v = fut.result()
        results[k] = v

os.makedirs("results", exist_ok=True)
with open("results/latest.json", "w") as f:
    json.dump(results, f)

keys = list(results.keys())
print(f"Merged {len(results)} results: {keys}")
