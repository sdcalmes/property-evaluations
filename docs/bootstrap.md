# New sessions and new properties

A fresh Work session should start by reading **AGENTS.md** on current main. The Project
instructions should explicitly name it; merely adding a file does not alter the app's
Project instruction field. The repository then supplies the detailed workflow.

```bash
python -m pip install -r requirements-research.txt
python -m property_eval.initialize --address '123 Example Ln, Sample, WI' \
  --listing-url 'https://example.org/actual-listing' --parcel-id 'VERIFIED-PARCEL'
```

Use the real address/source/parcel, not this example. Check the connected Sheet history
first. If the property already exists in either system, reuse/import that identity.
The initializer refuses a matching slug, primary address (including common street-type
abbreviations), normalized parcel, listing URL ignoring tracking, verified Sheet ID,
or existing output paths. Ambiguous address matches require review; there is no force
flag to bypass them. It does not geocode, establish active status or research facts.

It writes a canonical JSON record with `research_status: draft`, null unknowns, ratings
from the current profile, a matching narrative template, and *.draft.json research
skeletons. No placeholder facts/price/score/evaluation date are invented. These drafts
are excluded from the generated dashboard. They remain source files for the runner,
which can resolve them by slug/address/URL/parcel like any other record. Configure and
rename each verified preset to gis.json/photos.json/map.json before using it. Missing
configurations remain explicitly blocked rather than querying an example property.

After completing the actual evaluation and evidence review, replace the template
narrative, set the actual evaluation_date and `research_status: reviewed`, run validation,
tests and build, and publish normally. Do not promote a placeholder merely to make the
checks pass. Existing records lacking research_status remain reviewed for compatibility.

## Durable evidence between sessions

Private raw responses, photos, route inputs and ledgers are ignored working files, and
may disappear with a session. Reviewed public summaries live at
`data/evidence/<slug>.json`; the runner imports them idempotently on each session.
Validation automatically checks a summary when present. The current Laura Way summary
is transcribed from the completed Oct. 24 report, with its original observation dates;
it is not a claim of another live listing/municipal lookup. Older properties without a
summary still warn rather than gaining fabricated dates.

Log reviewed facts in the private ledger with `property_eval.evidence add` as described
in docs/workflow.md. Then explicitly select the IDs safe to retain publicly:

```bash
python -m property_eval.evidence_public --slug '<existing-slug>' \
  --ledger private/research/<existing-slug>/evidence.json \
  --ids '<observation-id>,<observation-id>' --reviewed
```

Use `--profile /path/to/private/buyer_profile.json` for additional private-address checks.
The --reviewed flag is the researcher's attestation after reviewing each selected
finding/source; it is not a request for an extra user approval. There is no export-all
mode. Allowlisted facts cover listing status/price, annual taxes, improvement documents,
small-shed permission, garden usability, parcel ID/exclusive acres/zoning, development
risk, photo review and comp condition. Raw source_capture entries, unrecognized facts,
known private addresses, credential-bearing/signed links, private route URLs and nested
private-input/cache fields are rejected. Keep unsupported facts as unknown/null.

Export retains existing reviewed observations, including differences/history, and never
changes the original observed_at dates. reviewed_at records this publication review,
not a new retrieval. Source links/dates/bases/notes and uncertainties remain available
across fresh sessions, with age/conflict warnings. Do not equate an allowlist/scan with
perfect privacy or source truth; review every value/link and any images before publishing.

## Master Database

Use [the verified Sheet contract and update procedure](master-sheet.md). The offline
preview helper never appends or writes to Google Sheets. Fresh reads, unique stable ID
matching, review and actual connector write/readback are still required. For a genuinely
new row, inspect formatting/validation/formulas and create it explicitly after completing
the evaluation. Do not sync draft placeholders. The repo cannot supply authentication
or make an unavailable connector work; report specific blockers honestly.
