#!/usr/bin/env python3
"""Optional weighted buyer-fit score. This is NOT a valuation model."""
import argparse, json
from pathlib import Path

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))

def score(record, profile):
    weights=profile["scoring"]["weights"]; ratings=record.get("ratings",{})
    total=used=0.0; details=[]
    for k,w in weights.items():
        if k not in ratings or ratings[k] is None: continue
        r=float(ratings[k])
        if not 0<=r<=10: raise ValueError(f"{k} must be 0-10")
        total += r*w; used += w; details.append({"criterion":k,"rating":r,"weight":w})
    s=round(total/used,2) if used else None
    flags=[]
    for k,label,cutoff in [("kitchen","Kitchen",5),("mudroom","Mudroom",4),("garage_outbuilding","Garage/outbuilding",4),("garden","Garden",4)]:
        if ratings.get(k) is not None and float(ratings[k])<=cutoff: flags.append(f"{label} is weak for this buyer profile.")
    return {"address":record.get("address"),"fit_score_0_to_10":s,
            "weight_coverage_percent":round(used/sum(weights.values())*100,1) if weights else 0,
            "details":details,"flags":flags,"uncertainties":record.get("uncertainties",[]),
            "warning":"Buyer-fit score only; do not use to derive market value or offer price."}

if __name__=="__main__":
    here=Path(__file__).resolve().parent
    p=argparse.ArgumentParser(); p.add_argument("record"); p.add_argument("--profile",default=str(here.parent/"buyer_profile.json"))
    a=p.parse_args(); print(json.dumps(score(load(a.record),load(a.profile)),indent=2))
