#!/usr/bin/env python3
"""
Parallel flight search via SerpAPI.
Reads PAYLOAD and SERPAPI_KEY from env, writes results/latest.json.

For each round-trip search it now:
  1. fetches the outbound list (1st SerpAPI call)
  2. for the first DIRECT outbound, follows its departure_token to fetch
     the return leg (2nd SerpAPI call) and parses direct return flights
Results are keyed by arrival_outbound_return so combinations no longer
overwrite each other.
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


def call_serpapi(params):
    url = "https://serpapi.com/search?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def base_params(s):
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
    return params


def direct_only(data):
    """Return parsed direct flights (single leg) from best+other."""
    out = []
    for f in (data.get("best_flights", []) or []) + (data.get("other_flights", []) or []):
        legs = f.get("flights", [])
        if len(legs) == 1:
            l = legs[0]
            out.append({
                "airline": l.get("airline"),
                "flight_number": l.get("flight_number"),
                "departure_time": l["departure_airport"]["time"],
                "arrival_time": l["arrival_airport"]["time"],
                "duration_min": f.get("total_duration"),
                "price": f.get("price"),
                "departure_token": f.get("departure_token"),
            })
    out.sort(key=lambda x: (x["price"] is None, x["price"]))
    return out


def fetch(s):
    # unique key per combination (bug fix: was keyed by return_date only)
    key = "{}_{}_{}".format(
        s["arrival_id"], s["outbound_date"], s.get("return_date", "oneway")
    )
    try:
        data = call_serpapi(base_params(s))
    except Exception as e:
        print(f"Error outbound: {key} | {e}")
        return key, {"error": str(e)}

    status = data.get("search_metadata", {}).get("status", "?")
    print(f"Done outbound: {key} | status={status}")

    outbound_direct = direct_only(data)
    data["outbound_direct"] = outbound_direct

    # follow the first direct outbound to get the return leg
    return_direct = []
    if s.get("return_date") and outbound_direct and outbound_direct[0].get("departure_token"):
        rp = base_params(s)
        rp["departure_token"] = outbound_direct[0]["departure_token"]
        try:
            rdata = call_serpapi(rp)
            return_direct = direct_only(rdata)
            # booking_token replaces departure_token on the return leg; drop it
            for r in return_direct:
                r.pop("departure_token", None)
            print(f"Done return:   {key} | {len(return_direct)} direct")
        except Exception as e:
            print(f"Error return:  {key} | {e}")
    data["return_direct"] = return_direct
    return key, data


results = {}
with ThreadPoolExecutor(max_workers=6) as ex:
    futures = {ex.submit(fetch, s): s for s in searches}
    for fut in as_completed(futures):
        k, v = fut.result()
        results[k] = v

os.makedirs("results", exist_ok=True)
with open("results/latest.json", "w") as f:
    json.dump(results, f)

print(f"Merged {len(results)} results: {list(results.keys())}")
