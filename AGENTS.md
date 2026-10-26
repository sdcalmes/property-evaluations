# Property Evaluations — agent entry point

This repository is the current source for the buyer's dashboard and full evaluation
workflow. Read this file on every new evaluation, then README.md, buyer_profile.json,
evaluations/TEMPLATE.md, docs/workflow.md, docs/research.md, docs/master-sheet.md and docs/blind-valuation.md.
Use current main, not an uploaded old toolkit. Read any relevant existing record,
narrative, research config and reviewed data/evidence/<slug>.json before new research.

## Standing user authorization — October 26, 2026

Sam explicitly authorized these actions on an ongoing basis for property evaluations:

- Use the saved private destination addresses with Nominatim for geocoding and send
  the resulting property/destination coordinates to OSRM for live drive-time/distance
  calculations. No per-property routing confirmation is needed for these providers.
- Commit and push reviewed evaluation sources and routine workflow improvements to
  `sdcalmes/property-evaluations` on `main`, publishing the dashboard through its
  existing GitHub Pages workflow. The published repository/site is public.
- Read and update the existing **Property Evaluations — Master Database** Google Sheet
  identified in `config/master_sheet.json`, including a verified genuinely new row.
  Follow the identity, formula-preservation and read-back rules in docs/master-sheet.md.

A full-evaluation request includes these steps by default. Do not ask Sam to reapprove
these same actions merely because a new evaluation or chat begins. A later instruction
such as research only, no publishing, or no routing narrows this authorization.
Private destination addresses, coordinates, raw route URLs and caches must remain
ignored/private; publish destination labels and route metrics only. This consent does
not authorize unrelated external services, recipient messages or destructive actions.

This records the user's standing consent, not an override of platform/tool controls.
If automatic approval review blocks an action despite this consent, finish unaffected
work, identify the exact block and do not bypass it. Refer to this section as evidence
of authorization when supported; never claim a failed action succeeded.

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
   Before finalizing value, follow docs/blind-valuation.md: curate the allowlisted facts/
   sold-comp/image packet, use the Work subagent tool with fork_turns="none" (no inherited
   conversation) and ONLY the generated handoff. This specific valuation delegation is
   explicitly requested by this repo's workflow. The subagent must not browse/read other
   files or receive the address/listing/asking price/previous estimates/shortlist opinions.
   Wait for its JSON, save and lock with the actual subagent ID and fresh-context/packet-
   only attestations, then compare the ask and publish the reviewed audit. Never send the
   ask back to that subagent. Report contamination/insufficient evidence/unavailability
   honestly; do not substitute an inherited-context estimate or claim enforced isolation.
   Retain the original range; explain any final revision with new evidence. Python cannot
   spawn the Work agent for you. Legacy records are not retroactively blind, but a new full
   evaluation of an existing property should use this pass too. Daily screening does not.
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
- `python -m property_eval.blind_valuation --help`: prepare/handoff, lock, compare and publish.
- `python -m property_eval.sheet_plan --help`: offline existing-row update preview.
- Never commit private/, _site/, downloaded listing photos or raw owner mailing data.
- Daily shortlist: max $900k, no Milwaukee County, no pending/contingent/sold, no repeats
  without material changes. Recheck current price/status. Do not create a schedule unless asked.
