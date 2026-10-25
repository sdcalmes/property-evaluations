# Blind valuation in a Work chat

The default full-evaluation workflow uses a **fresh-context, packet-only valuation
subagent**. It runs inside the existing Work chat without an API key or another app.
The research coordinator may see the asking price. The separate valuation subagent
must not receive that price, prior estimates, buyer fit scores or inherited chat history.
This is procedural blinding, **not an enforced tool/filesystem sandbox**. Shared tools,
files and ambient instructions remain accessible. Do not claim stronger isolation.

## Coordinator workflow

1. Research normally, including current asking price/status and verified sold comps.
   Preserve complete sources in the main evaluation/evidence, outside the blind packet.
2. Curate `private/research/<slug>/blind-input.json` from verified facts using the schema
   below. Build from the allowlist, not a raw listing/export with a few fields deleted.
   Keep location context material to value (municipality/neighborhood, street setting),
   but use Subject/C1/C2 IDs rather than full identifying addresses or live listing URLs.
   The script rejects unrecognized keys, pricing prose, URLs, currency cues, known
   excluded subject amounts in prose and private destination addresses. This is not
   semantic proof that every indirect price clue was removed: review the whole packet.
3. Inspect images for price overlays/portal UI. Use actual house photos, not portal
   screenshots. Every image input requires price_overlay_checked=true. The script
   creates anonymous JPEG copies with EXIF/metadata removed and content hashes.
   Original image paths and marketing filenames are not passed to the subagent.
4. Prepare the reviewed packet:

```bash
python -m property_eval.blind_valuation prepare --slug <slug> \
  --input private/research/<slug>/blind-input.json --reviewed
```

Optionally pass --profile /path/to/private/buyer_profile.json for extra address checks.
The output is an opaque `private/blind-valuations/<run-id>/` folder containing packet,
neutral images, handoff.txt and a coordinator-only private receipt. Do not show the
subagent coordinator.private.json, source record, whole folder listing or this conversation.

5. **The Work coordinator calls the actual subagent tool**, using `fork_turns: "none"`
   (or the available equivalent for a fresh context). Send only handoff.txt contents,
   including its embedded packet and exact allowed image paths. Do not prepend the
   address, asking price, target estimate, earlier valuation, buyer opinion or shortlist
   commentary. Do not fork the full conversation. If a no-history handoff is unavailable,
   record unavailable with a reason and label the final evaluation non-blind; do not
   silently substitute an inherited-context agent. Applicable repo instructions authorize
   this specific delegation; ordinary evaluation users need not request agents each time.
6. The subagent is instructed to read only supplied packet/images, do no browsing or
   other repository/file inspection, and return JSON. It must report contamination from
   ANY context or tool. These are instructions, not withdrawn tool permissions.
7. Save its returned JSON outside the run outputs, record its actual agent ID, then:

```bash
python -m property_eval.blind_valuation lock --run-dir <run-directory> \
  --result private/returned-valuation.json --agent-id <actual-subagent-id> \
  --fresh-context --packet-only
python -m property_eval.blind_valuation verify --run-dir <run-directory>
python -m property_eval.blind_valuation compare --run-dir <run-directory>
```

Lock writes result.json/lock.json once and refuses overwrite. Packet/image hashes must
match preparation; result must identify that packet/run. compare refuses an unlocked
or tampered run and reads the current record's asking price only after lock. The
coordinator already may know it; the subagent need never be told it. The command does
not fetch a fresh asking price or recommend an offer: the main agent verifies the price
and judges the final strategy. Changed material subject-record fields require a new pass.
If the reviewed packet itself changes, create a new run, never edit the old packet.

8. After public-content review, retain the audit and attach it to the same property:

```bash
python -m property_eval.blind_valuation publish --run-dir <run-directory> --reviewed
```

This saves `data/valuations/<slug>/<run-id>.json` with the sanitized packet, result,
hashes, timing, agent ID, handoff attestations and isolation limitation. Photo binaries
and coordinator receipts stay private. It updates only blind_valuation metadata in the
existing property record; it does NOT replace value/offer conclusions automatically.
Review narrative/summary/Sheet normally. The final report must show the original blind
range, compare the ask, and explain any change. If the final range differs, include
valuation_revision with reason, new_evidence and original_run_id. Prefer another fresh
blind pass when substantial new facts arrive; retain the earlier audit.

## Input schema

Top-level keys: as_of (YYYY-MM-DD), subject, comps, images (optional).

- Subject allowed fields: market_area (required neutral location description),
  property_type, year_built, beds, full_baths, half_baths, above_grade_sqft,
  below_grade_finished_sqft, exclusive_lot_acres, garage_spaces, garage_attached,
  condition, land, features, limitations, prior_sales. Unknowns are null.
- condition is an object of neutral kitchen/baths/roof/hvac/windows/siding/basement/overall
  observations. features/limitations are short text lists. land is neutral short text.
- prior_sales: completed subject sales only, each {sale_date, sale_price}. Verified
  previous sale prices are legitimate evidence; asking/relisting/offer prices are not.
- Each sold comp uses the same fields except prior_sales, plus comp_id (C1/C2/etc.),
  sale_date, sale_price, distance_miles and same_subdivision. Use only verified completed
  sales; retain source URLs/dates outside this packet. Do not select only comps supporting
  the ask or describe comps as cheap/expensive relative to it. No AVMs/assessments,
  current active-comp asking prices, previous value/offer ranges or buyer-fit ratings.
- images: [{path: '<local actual photo>', price_overlay_checked: true, property_id: 'Subject'}]. Images are
  optional; incomplete condition evidence must lower confidence or prevent valuation.
  Include relevant comp images if genuinely recovered, setting property_id to the
  included C1/C2 ID; anonymous image manifests retain that association (no source links).

The prepare command rejects unknown fields rather than silently dropping them. Typed
sale_price fields are preserved even if equal to an excluded subject asking price;
otherwise we would damage legitimate comp evidence or reveal the excluded price by
selectively changing a matching sale. Prose should not carry dollar amounts—use typed
sale fields. No automatic OCR claims are made; price-overlay checking is a real review.

## Result contract and failure states

handoff.txt embeds the exact JSON shape, packet hash and anonymous assets. A valued
result needs positive ordered low/mid/high, confidence low/medium/high, a rationale,
assumptions/missing evidence, and one comp_analysis entry per supplied comp. Each entry
has comp_id, weight (sum=1), adjusted_value (number or null) and reasoning explaining
important differences/adjustment direction. Unsupported dollar adjustments are not
required. At least two verified sold comps are needed for a numerical blind result.
The subagent may return insufficient_evidence with null values; do not pressure it to
hit an asking-price target. No offer strategy belongs in the blind result.

If the subagent encounters price/prior-valuation/outside-opinion evidence, report
contaminated with null values, explicit exposure and explanation. Exposed results cannot
be saved as valued. Start a corrected packet/new fresh agent; never ask it to forget an
observed price. If no fresh agent is available, set blind_valuation to
{method: work_subagent_packet_only, status: unavailable, reason: '<actual limitation>'}.
The report must say the final estimate is not a usable blind valuation in either case.

Hashes demonstrate which bytes were recorded and detect inconsistent edits, not that
an agent had no undisclosed context. The context/tool-use attestations are procedural
records; they are not independently verified by this Python script or a cryptographic
signature. Historic evaluations stay historic and are not retroactively called blind.

## Completion checks

New initializer records default to blind_valuation pending. Pending is allowed for drafts
but blocks a reviewed evaluation. The runner adds a blind checklist step; it cannot spawn
Work subagents from Python. Record validation verifies attached audit identities/hashes,
subject facts and value-range consistency/revision explanation. The property page labels
method, range and limitations. Existing legacy records without the new metadata remain
valid. The daily shortlist is still price-aware screening and must not run this workflow.
