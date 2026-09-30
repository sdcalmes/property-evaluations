#!/usr/bin/env python3
"""Rank comparable sales by similarity. Does not auto-value the subject."""
import argparse, csv, json
from datetime import date, datetime
from pathlib import Path

def num(v):
    try: return float(v) if str(v).strip() else None
    except: return None
def integer(v):
    try: return int(float(v)) if str(v).strip() else None
    except: return None
def truthy(v): return str(v).strip().lower() in {"1","true","yes","y"}
def clamp(x): return max(0,min(1,x))
def sim(s,c): return .5 if not s or not c else clamp(1-abs(c-s)/max(abs(s),1e-9))
def age_sim(s,c): return .5 if not s or not c else clamp(1-abs(c-s)/50)
def dist_score(m): return .4 if m is None else 1/(1+m/2)
def pdate(v):
    if not v: return None
    for f in ("%Y-%m-%d","%m/%d/%Y"):
        try: return datetime.strptime(v,f).date()
        except: pass
    raise ValueError(v)
def recency(d,asof): return .4 if d is None else .5**(max(0,(asof-d).days)/365)
def rank(subject,rows,asof):
    out=[]
    weights={"recency":.22,"distance":.20,"living_area":.16,"lot":.13,"age":.08,"garage":.06,"condition":.08,"setting":.07}
    for r in rows:
        sqft=num(r.get("living_area_sqft")); lot=num(r.get("lot_acres")); yr=integer(r.get("year_built")); gar=num(r.get("garage_spaces")); dist=num(r.get("distance_miles"))
        c={"recency":recency(pdate(r.get("sale_date")),asof),"distance":dist_score(dist),
           "living_area":sim(subject.get("living_area_sqft"),sqft),"lot":sim(subject.get("lot_acres"),lot),
           "age":age_sim(subject.get("year_built"),yr),"garage":sim(subject.get("garage_spaces"),gar),
           "condition":(num(r.get("condition_similarity")) or 5)/10,"setting":(num(r.get("setting_similarity")) or 5)/10}
        s=sum(c[k]*weights[k] for k in weights)
        s += .08 if truthy(r.get("same_street")) else (.04 if truthy(r.get("same_subdivision")) else 0)
        row=dict(r); row["match_score_0_to_100"]=round(min(1,s)*100,1)
        price=num(r.get("sale_price")); row["price_per_sqft"]=round(price/sqft,2) if price and sqft else ""
        row["match_components"]=json.dumps({k:round(v,3) for k,v in c.items()}); out.append(row)
    return sorted(out,key=lambda x:x["match_score_0_to_100"],reverse=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--subject",required=True); p.add_argument("--comps",required=True)
    p.add_argument("--output"); p.add_argument("--as-of"); a=p.parse_args()
    subject=json.loads(Path(a.subject).read_text(encoding="utf-8")); asof=date.fromisoformat(a.as_of) if a.as_of else date.today()
    with open(a.comps,newline="",encoding="utf-8-sig") as f: rows=list(csv.DictReader(f))
    ranked=rank(subject,rows,asof)
    import sys
    out=open(a.output,"w",newline="",encoding="utf-8") if a.output else sys.stdout
    if ranked:
        w=csv.DictWriter(out,fieldnames=list(ranked[0])); w.writeheader(); w.writerows(ranked)
    if a.output: out.close()
