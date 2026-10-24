# Property Evaluations — agent entry point

This repository is the current source for the buyer's dashboard and full evaluation
workflow. Read this file on every new evaluation, then README.md, buyer_profile.json,
evaluations/TEMPLATE.md, docs/workflow.md, docs/research.md and docs/master-sheet.md.
Use current main, not an uploaded old toolkit. Read any relevant existing record,
narrative, research config and reviewed data/evidence/<slug>.json before new research.

## Full eval {address or URL}

Install declared dependencies in a fresh environment: `python -m pip install -r requirements-research.txt`.

1. Identify the property using address, parcel and listing identity. Check the connected
   Master Database history too. Reuse matching records/rows; never create duplicates.
   If new, run `python -m property_eval.initialize --address '...' --listing-url '...'`
   with known parcel/slug/Sheet ID options as useful. It creates a draft and research
   config skeletons, not researched facts. Drafts are excluded from the dashboard.
2. Read the new research README; fill verified GIS/photo/map configs. Do not copy
   Laura Way's parcel, coordinates, setbacks or restrictions to another property.
3. Read the private Project buyer_profile.json for destination addresses; keep it in
   ignored private/ if a helper needs it. The public profile supplies current priorities,
   weights and labels. Never put private addresses/route URLs in public files or logs.
4. Run `python -m property_eval.research <slug>`. Missing inputs, access failures and
   partial captures are work to finish, not permission to omit a category. Use browser,
   HTTP/API and reasonable alternative public sources when helpful. Inspect actual
   photographs individually and strongest comparable interiors when accessible.
5. Follow the evaluation template. Verify current status/prices, sold comps/condition,
   GIS/environmental layers, garden/garage/shed restrictions, taxes/assessment, systems
   and three routes. Distinguish official records, claims, observations and inference.
   Unknown means null, not No. Keep source conflicts and dates. Do not anchor value to
   asking price, calculate it from buyer fit, or treat geometry fit as legal approval.
6. Garage first: usable 3+ car garage matters most. In subdivisions, prefer an existing
   or permitted small resin/wood garden shed; do not penalize no 30×40 workshop. Larger
   future shed is a bonus outside subdivisions/on larger lots. A 30×40 GARDEN remains
   high priority. Check dimensions, public/private restrictions and septic/reserve.
7. Review and update the same JSON and Markdown. Log important observations, retaining
   actual source dates. Explicitly select/review a public-safe evidence summary with
   property_eval.evidence_public; never copy a raw ledger or cache wholesale. Fresh
   sessions automatically load the committed summary; private raw captures may be gone.
8. When the substantive evaluation is complete, change research_status from draft to
   reviewed and set evaluation_date to the actual date. Do not promote a placeholder.
   Legacy records without research_status are treated as reviewed; do not bulk rewrite.
9. Unless the user requested research only/no publishing, run:
   `python -m property_eval.validate --public-sources`
   `python -m unittest discover -s tests -v`
   `python -m property_eval.build_site`
   Commit reviewed sources to this existing repo on main. Verify the actual Pages
   workflow result, then update/verify the matching Master Database row using the
   connected Sheets tools and documented ID/column/formula rules. Do not claim an
   attempted write/deploy succeeded. Report a concrete blocker and preserve completed work.

Research capture completion is not evaluation completion. The runner does not inspect
photos, interpret legal rights, value a property, update the Sheet or publish for you.
Default publishing of completed evaluations is authorized; routine steps do not need
another user confirmation. Respect narrower instructions and explicit exclusions.

## Commands / completion evidence

- `python -m property_eval.initialize --help`: duplicate-safe new drafts.
- `python -m property_eval.research <slug>`: capture/resume and unresolved checklist.
- `python -m property_eval.evidence_public --help`: reviewed evidence export.
- `python -m property_eval.sheet_plan --help`: offline existing-row update preview.
- Never commit private/, _site/, downloaded listing photos or raw owner mailing data.
- Daily shortlist: max $900k, no Milwaukee County, no pending/contingent/sold, no repeats
  without material changes. Recheck current price/status. Do not create a schedule unless asked.
