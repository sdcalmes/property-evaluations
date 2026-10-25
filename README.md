# Property Evaluations

**Agents: start with [AGENTS.md](AGENTS.md) on current main.** [Fresh-session/new-property setup](docs/bootstrap.md) covers duplicate-safe drafts, reviewed evidence retained between sessions, and the [Master Database update procedure](docs/master-sheet.md).

A small, repo-backed buyer research workflow. ChatGPT Work researches a property and writes two reviewed files: a structured JSON summary and the full Markdown evaluation. Python builds a static dashboard and detail pages; GitHub Actions tests and deploys those pages. Research and valuation remain human analysis, not automatic output from the helpers.

The repository starts without production property records. No past evaluations have been guessed or imported.

## Add or update a property

1. Research the property using the Project's private buyer profile and `evaluations/TEMPLATE.md`. Check current status, photos, sale comps, land constraints, taxes, and the three commute destinations. Save the narrative at `evaluations/<slug>.md`.
2. Save its summary at `data/properties/<slug>.json`. The `slug` and `evaluation_markdown` fields must agree with the filenames. Use `null` for unknown facts, never `false` or "No" as a substitute for missing evidence. Avoid private destination street addresses in the narrative or summary.
3. Run tests and build. Review `_site/index.html` and `_site/properties/<slug>/index.html`; commit both source files. Push to `main` to deploy.

Minimal record example (illustrative only; no synthetic record is committed to production data):

```json
{
  "slug": "123-example-lane",
  "address": "123 Example Lane, Sample, WI",
  "listing_url": null,
  "status": null,
  "current_list_price": null,
  "original_list_price": null,
  "beds": null,
  "baths": null,
  "year_built": null,
  "above_grade_sqft": null,
  "below_grade_finished_sqft": null,
  "garage": null,
  "lot_acres": null,
  "utilities": null,
  "hoa": null,
  "annual_taxes": null,
  "ratings": {},
  "buyer_fit_score": null,
  "estimated_value_low": null,
  "estimated_value_high": null,
  "pricing_conclusion": null,
  "opening_offer": null,
  "reasonable_range": null,
  "caution_price": null,
  "walk_away_price": null,
  "commutes": [],
  "major_positives": [],
  "major_concerns": [],
  "uncertainties": [],
  "evaluation_date": "2026-09-29",
  "evaluation_markdown": "123-example-lane.md"
}
```

`lot_acres` means **exclusive** parcel acreage. Describe undivided/common land separately in the narrative and, if useful, a future optional field. Keep above-grade and finished below-grade area separate. Record meaningful source conflicts and the source/date in the Markdown; do not silently pick a winner. Mapped wetland is not a surveyed delineation. `buyer_fit_score` is a convenience score, **not** a value estimate. Comp similarity helps prioritize analysis but never calculates an offer.

`commutes` contains result labels only, for example `{"destination":"Lisa's Work","candidate_minutes":38,"impact":"materially worse"}`. This public repository's `buyer_profile.json` contains criteria, weights, labels, and commute baselines, but **no destination street addresses**. The full route addresses remain in the private ChatGPT Project profile. Source JSON and Markdown are public too, so review them before committing. The build checks the generated site against hashed known private street lines and fails if it finds one.

## Local commands

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m property_eval.build_site
```

Open `_site/index.html` in a browser. Generated links use `/property-evaluations/`, so use `python -m http.server` from a parent directory with `_site` copied or symlinked to `property-evaluations` for a full local navigation check. To build for a root path in a local preview: `python -m property_eval.build_site --base-path /`.

Optional toolkit helpers:

```bash
python -m property_eval.scoring data/properties/<slug>.json
python -m property_eval.comps --subject subject.json --comps comps.csv
python -m property_eval.routing --subject "Property address" --format json
```

Scoring uses the buyer profile weights and renormalizes missing ratings. For optional local routing, copy the Project's full `buyer_profile.json` to `private/buyer_profile.json` (ignored by Git), or pass its path with `--profile`. The routing helper uses public Nominatim/OSRM without traffic by default, or Google Routes with `GOOGLE_MAPS_API_KEY`; it may fail in restricted networks. Its geocode cache is local working data and should be reviewed before committing new entries. Comps are supplied manually as a CSV; the tool only ranks them.

## Deployment

`.github/workflows/pages.yml` tests, builds `_site`, uploads it as a Pages artifact, and deploys on a push to `main` (or a manual workflow run on `main`). `_site` is ignored by Git. Set **Settings → Pages → Build and deployment → Source: GitHub Actions** if GitHub has not selected it. The expected project URL is `https://sdcalmes.github.io/property-evaluations/`. A private repository's Pages availability depends on the GitHub account/plan; the published site itself should be treated as public.

## Independent valuation stage

Full evaluations now use a [fresh-context Work valuation subagent](docs/blind-valuation.md)
with a reviewed, asking-price-free packet before final comparison. No separate API key
is required. The coordinator must perform the actual fresh subagent handoff; Python
prepares/verifies/locks artifacts but cannot spawn Work agents. Shared files/tools remain
accessible: this is procedural blinding, not an enforced sandbox. New drafts default to
pending; historical evaluations are not retroactively relabeled. Daily screening stays
price-aware and does not perform this valuation stage.

## Research runner

```bash
python -m property_eval.research n52w26889-laura-way
python -m property_eval.validate --public-sources
```

[Runner, evidence ledger and validation guide](docs/workflow.md): resume existing-property research, retain source dates/conflicts, and generate an unresolved-items checklist. Defaults run GIS, reviewed photo manifest, map, optional private-profile routing and checks. Missing inputs are reported; the runner does not alter reviewed evaluations or Sheet rows. Routing now compares static times with static baselines and keeps traffic estimates separate.

## Repeatable research and storage priorities

[Research workflow and commands](docs/research.md) cover resumable ArcGIS capture, browser-response imports when HTTP is blocked, photo discovery/download/validation, numbered photo review sheets, and annotated parcel maps. Install optional dependencies with `python -m pip install -r requirements-research.txt`. Laura Way has reusable configs under `research/n52w26889-laura-way/`. Keep raw captures and photos under ignored `private/research/`; publish reviewed conclusions and maps.

Buyer storage priorities were clarified October 24, 2026: a usable **3+ car garage** is the main priority; external storage matters less with that garage. In subdivisions, ideally combine it with an existing/permitted small resin or wood garden shed. Do **not** require or penalize absence of a 30×40 workshop. Outside subdivisions or on larger lots, a future larger shed is a bonus. The **30×40 garden** remains high priority. Public/private rules still apply to small sheds. See `buyer_profile.json` for scoring guidance; weights remain unchanged.

Research interpretation, photo inspection, comp selection, valuation/offers, production record updates and Master Database row updates remain reviewed work. These helpers capture evidence; they do not auto-score properties, approve construction, or create duplicate records. The connected master Google Sheet retains evaluation history; the repo supplies this dashboard.
