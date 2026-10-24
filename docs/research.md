# Repeatable property research

For the combined command, resumability, evidence ledger and checks, see [the workflow guide](workflow.md).

These helpers capture evidence; they do not decide zoning legality, hidden condition,
value, or buyer-fit scores. They operate on existing property slugs without writing
production evaluations or adding database rows automatically.

## Setup and layout

```bash
python -m pip install -r requirements-research.txt
```

Run from the repository root. Keep source configs and observed public photo URLs in
`research/<slug>/`. Keep raw GIS responses, downloaded photographs, rendered HTML,
review notes, route inputs and intermediate maps in **ignored** `private/research/<slug>/`.
Publish only reviewed conclusions and an annotated map when appropriate. Do not commit
listing photo binaries or raw owner mailing data. Never put private destination
addresses in a public source config.

The Laura Way configs are a worked example, not defaults for other properties.
The EPSG:6609 county projection uses feet. Do not use latitude/longitude as feet.
Endpoint/layer IDs and historical contour/wetland dates need verification each run.

## 1. GIS capture

```bash
python -m property_eval.gis \
  --config research/n52w26889-laura-way/gis.json \
  --cache private/research/n52w26889-laura-way/cache \
  --out private/research/n52w26889-laura-way/gis-bundle.json
```

The helper verifies a unique parcel ID, requests object IDs, retrieves features in
bounded batches, queries the parcel polygon for configured thematic layers and a
buffered envelope for neighbors. It retains original attributes/geometries, source
URLs, actual UTC capture times, and separate layer errors. Nonzero exit 2 means a
partial bundle: failed layers are **unknown**, never evidence of no constraint.
A successful empty query means only no mapped intersection in that layer/version.
It does not replace a wetland delineation or establish freedom from deed restrictions.

Responses are cached by the exact query URL hash. Reruns resume without new calls;
use `--refresh` to intentionally refetch. `assembled_at` is not a new observation date:
the per-source `captured_at` timestamps remain authoritative. Preserve historical
bundles separately before refreshing. Queries return complete intersecting features,
so county contour polylines can be large. The renderer clips them to the parcel.

To retrieve service/layer metadata through the same cached transport:

```bash
python -m property_eval.gis --inspect 'https://gis.waukeshacounty.gov/host/rest/services/Basemap_Reference_Service/MapServer' --cache private/research/discovery --out private/research/discovery/basemap.json
```

To discover services, open the county REST directory with `?f=pjson`, then inspect
a service's `layers` list and each candidate layer's `fields`, `geometryType`,
`spatialReference`, `maxRecordCount` and description. For example:

- <https://gis.waukeshacounty.gov/host/rest/services?f=pjson>
- <https://gis.waukeshacounty.gov/host/rest/services/Basemap_Reference_Service/MapServer?f=pjson>
- <https://gis.waukeshacounty.gov/host/rest/services/Web_Tax_Parcel/MapServer/2?f=pjson>

Copy a config for another parcel. Verify field names, SR/units, endpoints, area queried,
and dates; county layers are not portable to other jurisdictions. Nearby large fields
can extend far beyond the envelope and their centroid zoning may differ from the
subject's. Map polygons and distinguish intersected/sampled zoning. Tax owner identity
is not evidence of conservation or development approval.

### When local HTTP is blocked

Some Work sessions can open county URLs in the browser while script HTTP gets 403.
The helper leaves `cache/pending-request.json` containing the exact requested URL and
cache destination. Open that URL using Work's authorized browser, save the actual JSON
response to an ignored local file, and import it:

```bash
python -m property_eval.research_io \
  --pending private/research/n52w26889-laura-way/cache/pending-request.json \
  --response private/research/n52w26889-laura-way/browser-response.json \
  --captured-at '2026-10-24T18:30:00Z'
```

Supply the **actual** retrieval time, not this example. Rerun the GIS command without
`--refresh`. Repeat for subsequent pending requests. Do not import access walls or
invent data. If multiple optional layers fail, run with a narrowed config to import
one at a time (pending-request records the last attempted URL). Work can save JSON
from a browser-visible API response; no special county credentials are required.
The code deliberately cannot bypass CAPTCHA, access control or sign-in requirements.

## 2. Listing photos

```bash
python -m property_eval.photos discover \
  --url 'https://www.coldwellbankerhomes.com/wi/lisbon/n52w26889-laura-way/pid_74389896/' \
  --out private/research/n52w26889-laura-way/photo-candidates.json
```

Discovery reads img/lazy src/srcset, OpenGraph and JSON-LD. Inspect the candidate
manifest and remove ads, logos, other-property photos and duplicates; verify the actual
gallery count/order. It is a candidate extractor, not a guaranteed listing scraper.
For browser-only galleries, save rendered HTML and add `--html path/to/page.html`,
or save `{listing_url, discovered_at, images:[{src, alt}]}` directly from the observed
gallery URLs. A read-only DOM expression useful for candidates is:

```javascript
Array.from(document.querySelectorAll('img')).map(img => ({
  src: img.currentSrc || img.getAttribute('data-src') || img.src,
  alt: img.alt
})).filter(img => /^https?:/.test(img.src))
```

Open the actual gallery and advance through all images if only active slides are
in the DOM. Inspect `srcset`/full-size links rather than guessing image URL patterns.
The checked-in Laura Way `photos.json` preserves all 35 observed Oct. 24 URLs,
including some thumbnails. Future URLs/gallery availability may change.

```bash
python -m property_eval.photos download \
  --manifest research/n52w26889-laura-way/photos.json \
  --out private/research/n52w26889-laura-way/photos
python -m property_eval.photos review --out private/research/n52w26889-laura-way/photos
```

Downloads resume by URL/hash, validate image content (not HTTP status alone), retain
source/time/SHA-256/dimensions, flag duplicate content and images below 900 pixels,
and report individual failures with exit 2. `review.html` shows numbered contact sheets,
individual full downloaded images and original-source links. Inspect every image;
a contact sheet alone is insufficient. Small files remain labeled thumbnails.
Do not call cosmetic refreshing a full renovation without evidence. Photographs do
not verify system age/operation, structural soundness or moisture history.

If the image CDN blocks scripts, download the observed images via Work's browser,
naming them `001.webp`, `002.jpg`, etc. in manifest order in an ignored directory.
Import that batch through the same image validation/provenance pipeline:

```bash
python -m property_eval.photos download --manifest research/n52w26889-laura-way/photos.json --out private/research/n52w26889-laura-way/photos --import-dir private/research/n52w26889-laura-way/browser-images --captured-at '2026-10-24T18:30:00Z'
```

Use the actual time for that download batch; split batches/manifests if capture dates
differ. Missing numbers fail explicitly. Browser filenames must match manifest order;
verify each image against the source gallery. The automated downloader cannot reuse
a cloud browser session or overcome a host/network access restriction.

## 3. Annotated parcel map

```bash
python -m property_eval.parcel_map \
  --bundle private/research/n52w26889-laura-way/gis-bundle.json \
  --config research/n52w26889-laura-way/map.json \
  --out private/research/n52w26889-laura-way/parcel-study.png
```

The default Laura preset shows a **30×40 garden** and an illustrative **10×12 garden
shed**, rather than treating a 30×40 workshop as a requirement. 10×12 is an example,
not a buyer minimum or municipal exemption. Optional previous workshop study positions
remain in `map-workshop-alternatives.json` for deliberate further analysis.

Config coordinates are explicit projected feet. Manually identify street-side edges
from the polygon/aerial/survey; do not assume polygon vertex indices generalize.
Set title, street guides, dimensions/rotation, labels and source note per property.
Street bands are illustrative offsets from supplied mapped edges, **not verified legal
ROW/base setback lines**. Default 50-ft bands are Laura-specific study guides, not a
countywide setback rule. Output includes footprint containment, building overlap and
nearest mapped-building/street-edge distances in a sidecar metrics JSON. Metrics also
include parcel area/perimeter/bounding extent, building footprint/edge separation,
street-guide lengths, crossing-contour elevation range, per-feature zoning overlap
(including small boundary artifacts), layer counts/errors and original source dates. None is a
legal approval. Actual buildability still needs septic/reserve, easements, setbacks,
covenants, height/material/foundation/use rules, access and municipal review. A small
resin/portable shed may still be regulated. Contours are historical, not a site grading
plan. The map is a schematic GIS study, not licensed aerial imagery or a survey.

Review the PNG visually and metrics before promoting a map to `evaluations/assets/`.
Never label a guessed mound, reserve area, wetland or unverified tree line as surveyed.
Keep conflicting sources and unknowns in the evaluation. Invalid parcel/building geometry
fails rather than being silently repaired. Laura's county zoning includes degenerate
zero-area rings and tiny self-intersections. The preset explicitly enables
`repair_invalid_thematic_geometry`: Shapely make_valid retains polygonal parts and
records every reason/area-before/area-after in the sidecar metrics. Review those
repairs and boundary artifacts before drawing conclusions; originals remain in the
bundle. Disable this opt-in to require strictly valid zoning polygons.

## 4. Complete the existing record

Use the current buyer profile and evaluation template. Apply storage guidance once
under `garage_outbuilding`; no extra penalty for missing optional workshop potential.
Review evidence, source dates, comps and pricing independently. Update existing JSON
and Markdown, then update the existing Master Database row by property ID. Helpers
intentionally do not automatically change prices, ratings, production records or Sheet
rows. Do not bulk rescore past evaluations without reviewing the underlying evidence.

```bash
python -m property_eval.scoring data/properties/n52w26889-laura-way.json
python -m unittest discover -s tests -v
python -m property_eval.build_site
```

Commit reviewed sources on main; verify the actual Pages workflow/deployment result.
