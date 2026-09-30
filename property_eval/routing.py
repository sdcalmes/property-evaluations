#!/usr/bin/env python3
"""Optional local drive-time comparison helper for Property Evaluations.

This script requires outbound internet access. Some ChatGPT/Python runtimes block
outbound network calls, so property evaluations must not depend on this script
succeeding. If it fails, use live web/map routing research and still compare the
candidate property with the saved baselines in buyer_profile.json.

Default: Nominatim geocoding + OSRM routing (free, no traffic).
Optional: Google Routes API traffic-aware routing with GOOGLE_MAPS_API_KEY.

Examples:
  python drive_times.py --subject "S23W26149 Canterbury Ln, Waukesha, WI 53188"
  python drive_times.py --subject "..." --provider google
  python drive_times.py --subject "..." --provider google --departure 2026-08-18T07:45:00-05:00
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

MILES_PER_METER = 0.000621371
USER_AGENT = "PropertyEvaluationToolkit/1.0 (personal residential research)"

def load_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def save_json(path, data): Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

def http_json(url, headers=None, body=None, timeout=20):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def geocode(address, cache_path, refresh=False):
    cache_path = Path(cache_path)
    cache = load_json(cache_path) if cache_path.exists() else {"schema_version": 1, "locations": {}}
    key = address.strip().lower()
    if not refresh and key in cache["locations"]:
        r = cache["locations"][key]
        return float(r["latitude"]), float(r["longitude"])
    q = urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": 1, "countrycodes": "us"})
    result = http_json("https://nominatim.openstreetmap.org/search?" + q, {"User-Agent": USER_AGENT})
    if not result: raise RuntimeError(f"Could not geocode: {address}")
    lat, lon = float(result[0]["lat"]), float(result[0]["lon"])
    cache["locations"][key] = {"address": address, "latitude": lat, "longitude": lon,
                               "display_name": result[0].get("display_name"), "provider": "nominatim"}
    save_json(cache_path, cache)
    time.sleep(1.05)
    return lat, lon

def route_osrm(origin, destination):
    olat, olon = origin; dlat, dlon = destination
    coords = f"{olon},{olat};{dlon},{dlat}"
    data = http_json("https://router.project-osrm.org/route/v1/driving/" + coords + "?overview=false&steps=false",
                     {"User-Agent": USER_AGENT})
    r = data["routes"][0]
    return {"duration_minutes": r["duration"]/60, "distance_miles": r["distance"]*MILES_PER_METER,
            "provider": "osrm", "traffic_aware": False}

def seconds_string_to_minutes(value):
    return float(value[:-1]) / 60 if value.endswith("s") else float(value)

def route_google(origin_address, destination_address, departure=None):
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key: raise RuntimeError("GOOGLE_MAPS_API_KEY is not set.")
    body = {"origin":{"address":origin_address},"destination":{"address":destination_address},
            "travelMode":"DRIVE","routingPreference":"TRAFFIC_AWARE","units":"IMPERIAL"}
    if departure: body["departureTime"] = departure
    data = http_json("https://routes.googleapis.com/directions/v2:computeRoutes",
                     {"Content-Type":"application/json","X-Goog-Api-Key":key,
                      "X-Goog-FieldMask":"routes.duration,routes.distanceMeters,routes.staticDuration"}, body)
    r = data["routes"][0]
    return {"duration_minutes": seconds_string_to_minutes(r["duration"]),
            "static_duration_minutes": seconds_string_to_minutes(r["staticDuration"]) if r.get("staticDuration") else None,
            "distance_miles": r["distanceMeters"]*MILES_PER_METER, "provider":"google","traffic_aware":True}

def impact(delta, baseline, profile):
    cfg = profile.get("location_comparison", {})
    threshold = min(float(cfg.get("material_change_minutes",5)),
                    baseline*float(cfg.get("material_change_percent",15))/100)
    threshold = max(3.0, threshold)
    if delta <= -threshold: return "materially better"
    if delta >= threshold: return "materially worse"
    if delta < -1: return "slightly better"
    if delta > 1: return "slightly worse"
    return "about the same"

def evaluate(subject, profile, provider, cache, departure=None, refresh=False):
    rows=[]; subject_coords = geocode(subject, cache, refresh) if provider=="osrm" else None
    for key,d in profile["destinations"].items():
        baseline=float(d["baseline_no_traffic_minutes"])
        route = route_google(subject,d["routing_address"],departure) if provider=="google" else route_osrm(subject_coords,geocode(d["routing_address"],cache,refresh))
        duration=float(route["duration_minutes"]); delta=duration-baseline
        rows.append({"destination":d["label"],"baseline_minutes":round(baseline,1),
                     "candidate_minutes":round(duration,1),"delta_minutes":round(delta,1),
                     "distance_miles":round(route["distance_miles"],1),"impact":impact(delta,baseline,profile),
                     "provider":route["provider"],"traffic_aware":route["traffic_aware"]})
    return rows

def main():
    here=Path(__file__).resolve().parent
    p=argparse.ArgumentParser()
    p.add_argument("--subject",required=True); p.add_argument("--profile",default=str(here.parent/"private/buyer_profile.json"))
    p.add_argument("--cache",default=str(here.parent/"location_cache.json")); p.add_argument("--provider",choices=["osrm","google"],default="osrm")
    p.add_argument("--departure"); p.add_argument("--refresh-geocodes",action="store_true"); p.add_argument("--format",choices=["table","json","csv"],default="table")
    a=p.parse_args()
    if not Path(a.profile).is_file():
        p.error("routing needs a private profile; copy the Project buyer_profile.json to private/buyer_profile.json (gitignored), or pass --profile")
    profile=load_json(a.profile)
    rows=evaluate(a.subject,profile,a.provider,a.cache,a.departure,a.refresh_geocodes)
    if a.format=="json": print(json.dumps({"subject":a.subject,"routes":rows},indent=2))
    elif a.format=="csv":
        w=csv.DictWriter(sys.stdout,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    else:
        print(f"Subject: {a.subject}\nProvider: {a.provider}\n")
        print(f"{'Destination':<20} {'Baseline':>9} {'Candidate':>10} {'Change':>8} {'Miles':>7}  Impact")
        for r in rows:
            print(f"{r['destination']:<20} {r['baseline_minutes']:>8.1f}m {r['candidate_minutes']:>9.1f}m "
                  f"{r['delta_minutes']:>+7.1f}m {r['distance_miles']:>6.1f}  {r['impact']}")
if __name__=="__main__": main()
