# Research runner, evidence and checks

From the repo root, install `requirements-research.txt`. The research runner combines
the existing GIS, photo, map, route and validation helpers:

```bash
python -m property_eval.research n52w26889-laura-way
```

An exact existing address, parcel ID or saved listing URL also works. A target must
resolve to exactly one existing record. Unknown/ambiguous targets stop; this command
never creates a production record, changes a score/value, writes a Sheet row or deploys.
For a new property, use `property_eval.initialize` to create a duplicate-checked draft, configure it, and complete the research before marking it reviewed. See docs/bootstrap.md. Drafts are excluded from the dashboard.

## Configuration and outputs

- Public per-property presets: `research/<slug>/gis.json`, `photos.json`, `map.json`.
- Private routing inputs: `private/buyer_profile.json`, or `--profile /path/to/private.json`.
- Private working outputs: `private/research/<slug>/` (already ignored by Git).
- Missing presets/profile produce explicit blocked steps, while independent work continues.
- Photo discovery stays a separate reviewed step: inspect candidates/gallery count before
  making `photos.json`. The runner does not auto-download unrelated discovery candidates.

Outputs include `run.json`, `checklist.md`, `evidence.json`, `evidence-report.json`,
`validation.json`, GIS bundle, image review sheets, annotated map/metrics and route JSON.
The checklist includes the questions that still require documents or human inspection.

```bash
# Run available land/photo research without routing.
python -m property_eval.research n52w26889-laura-way --steps gis,photos,map,checks
# Reuse matching completed captures without making network calls.
python -m property_eval.research n52w26889-laura-way --steps gis,photos,map,checks --offline
# Deliberately refetch selected captures. Archive working evidence first if needed.
python -m property_eval.research n52w26889-laura-way --steps gis,photos --refresh
```

Resume uses input/config/tool-code hashes and checks output hashes, including downloaded
images and contact sheets. Missing/corrupt outputs invalidate reuse. Failed/partial steps
are retried, not labeled successful. A failed GIS refresh blocks mapping an older bundle.
Checks always rerun so freshness advances with time. Existing source capture dates remain
unchanged when data is reused. Ordinary reruns can reuse old HTTP caches; freshness
warnings tell the reviewer when an intentional `--refresh` is needed. Offline mode only
reuses completed matching runner captures; import browser responses/downloads with the
[research helpers](research.md), then run the normal command to assemble them first.

Exit 0 means selected capture/check steps succeeded, **with human review still required**.
Exit 2 means missing, blocked, failed or partial work; inspect `run.json`/`checklist.md`.
Validation warnings are not errors and are preserved for review. A command with only
`--steps checks` is not evidence that GIS/photos/routes were acquired. Earlier steps
remain in run history, while `selected_steps` identifies the current invocation.

## Evidence ledger

Observations are append-only and deduplicated by content/source/date. They retain the
fact, JSON value, source URL, actual observation date, source kind, evidence basis,
optional event date and note. New observations never silently replace conflicting old
ones. A different value can be a legitimate price/history change; explain it rather
than treating every conflict as an error.

```bash
python -m property_eval.evidence \
  --ledger private/research/n52w26889-laura-way/evidence.json \
  --slug n52w26889-laura-way add \
  --fact listing.status --value '"Active"' \
  --source-url 'https://example.org/actual-observed-listing' \
  --observed-at '2026-10-24T18:30:00Z' --basis listing_claim --kind listing
python -m property_eval.evidence \
  --ledger private/research/n52w26889-laura-way/evidence.json \
  --slug n52w26889-laura-way report
```

Use the actual source/date/value, not the illustrative example. A date-only source is
retained as date-only and treated as UTC midnight for conservative age checks. Separate
a 2020 roof installation (`event_date`) from the date its documentation was retrieved
(`observed_at`). `unknown` requires null and can omit the URL; known evidence needs an
HTTP(S) source. Supported bases: official_record, listing_claim, visual_observation,
inference, source_capture, unknown. An automatically downloaded photo is **source_capture**,
not a claim that its interior was inspected. Add actual findings separately after review.

The ledger flags future/invalid dates, mutated observations, stale sources, differing
values, explicit unknowns and missing essential facts. Default review ages are listing
1 day, route 7, photo 30, GIS/permit/document 365, tax 400 and analysis 30 days. These
are review prompts, not guarantees that data remains accurate until the threshold.
GIS no-intersection results are raw map evidence, not buildability or wetland approval.
The runner imports a reviewed data/evidence/<slug>.json summary when available, retaining original dates across sessions. Use property_eval.evidence_public to export explicitly selected, reviewed findings; do not commit raw ledgers. The runner does not pretend historical reports have a complete machine-readable ledger;
important listing/tax/improvement/shed/garden findings must be logged or stay missing.

## Validation and publication

```bash
python -m property_eval.validate --slug n52w26889-laura-way \
  --ledger private/research/n52w26889-laura-way/evidence.json
python -m property_eval.validate --public-sources
python -m unittest discover -s tests -v
python -m property_eval.build_site
```

Errors include helper/record score or coverage mismatch, invalid numeric ratings/prices,
reversed value/caution/offer ranges, duplicate property identity, filename mismatch,
missing narrative, private commute address fields, known private street addresses and a
structured subdivision record requiring a large workshop. Warnings flag acreage conflicts,
old traffic/baseline comparisons, absent/stale/differing evidence, and targeted suspicious
workshop wording. This is not a full semantic checker of prose, title rights, costs or value.
The source scan examines Git-tracked and nonignored UTF-8 text; binary files require
separate review. CI now runs these checks before the static build/deploy. Historical
records without ledgers emit warnings instead of fabricated provenance or mass changes.

## Routing correction

```bash
python -m property_eval.routing --subject 'Property address' --provider google \
  --profile private/buyer_profile.json --departure '2026-11-02T13:30:00Z' --format json
```

Google requires `GOOGLE_MAPS_API_KEY`. Choose a real future departure with a timezone;
Google may reject historical times. Output retains traffic-aware candidate time and
static candidate time separately. `delta_minutes`/`impact` compare **static candidate
against saved no-traffic baseline**, with `comparison_basis=static_to_static`. If static
Google time is missing, delta is null; it never substitutes traffic time for that comparison.
The saved baseline is not a freshly rerouted current-home trip. OSRM remains traffic-free.
Default geocode cache now lives in ignored `private/location_cache.json`; the runner
uses its own ignored working cache. Destination labels/results are public-safe outputs;
private input/cache files remain private. No fresh commute measurements are implied by
this code change; existing historical evaluation commute entries remain as recorded.
