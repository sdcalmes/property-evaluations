# Master Database update procedure

The connected Google Sheet **Property Evaluations — Master Database** is evaluation
history. This repo supplies the public dashboard. Use connected Sheets tools, not a
local Excel/CSV snapshot as the current source. Read `config/master_sheet.json` for
verified spreadsheet/tab identifiers and the exact 54-header contract (Oct. 24, 2026).
Never read/export the private Destinations tab for a property update.

## Identify first

1. Read spreadsheet metadata and Properties!A1:BB1. Verify the title, tab ID and exact
   headers against config. If changed, inspect and update the mapping; do not guess.
2. Read the populated Property ID column in bounded ranges (for example A2:A100,
   expanding until all populated IDs are covered). Check address/MLS history for
   possible existing records as needed. IDs do not have a single slug-derived format.
3. Store the verified existing ID in the property's `master_database_id`. Laura Way's
   is `N52W26889-LAURA`. Find its row live; **27 is not a permanent row identity**.
   Stop on duplicate/ambiguous matches. If a property exists only in Sheet history,
   import/research that same identity rather than treating it as a new property.

## Existing-row update

Read the target A:BB row with UNFORMATTED_VALUE. Also use CellData on AY:BB to retain
actual formula expressions, not just displayed values. Save a private snapshot:

```json
{
  "spreadsheet_id": "<from config>",
  "sheet_name": "Properties",
  "start_row": 27,
  "headers": ["<exact header row, all 54 columns>"],
  "rows": [["<actual freshly read row values>"]]
}
```

`start_row` is 1-based and records where the bounded data rows came from, excluding
the separately supplied header. The helper checks identity only inside that snapshot;
the agent must establish global ID uniqueness before applying it.

```bash
python -m property_eval.sheet_plan \
  --record data/properties/n52w26889-laura-way.json \
  --snapshot private/sheet-snapshot.json \
  --patch private/sheet-reviewed-patch.json \
  --out private/sheet-update-plan.json
```

`--patch` is optional and contains reviewed `{header: value}` overrides for fields
requiring judgment (Shed, Location Summary, Major Concerns, Data Quality Notes, etc.).
Only provided, known direct record fields are mapped automatically. Null record fields
are skipped, not converted to No or used to erase history. Review whether a stale old
value needs manual correction/clearing; skipping null is not proof the old value is
still accurate. Offer endpoints, total finished area, state/ZIP and qualitative fields
need explicit reviewed mapping when not supplied by the direct-field contract. The
helper never parses dollar prose, garage strings or full addresses into invented facts.

The preview includes exact cell changes, old values, ID/header preconditions and
structured connector arguments. It executes no network writes. Rejects missing/duplicate
IDs in the snapshot, header drift, formula-column/ID edits, draft records, invalid values
and automatic null clearing. Values use stringValue/numberValue/boolValue, never an
untrusted formulaValue. The metadata check plus configured ID prevents writing another
spreadsheet/tab. Use `--profile` with the private profile for additional address checks.

Before applying, re-read headers, global ID uniqueness and each changed cell's old value.
If the row moved or anything changed, regenerate. This is not atomic compare-and-swap;
Sheets has no conditional cell-write lock in this procedure. Minimize the read/write gap.
Apply `connector_arguments` through the connected batch_update_spreadsheet tool.
Update only userEnteredValue for planned B:AX cells. Read back changed values, stable
ID and AY:BB formulas; only then report success. Retain snapshot/plan/receipt privately.
A successful preview is not a successful Sheet update.

## Protected computed columns

| Column | Header | Existing formula role |
|---|---|---|
| AY | Value Mid | Average AK:AL when both exist |
| AZ | Ask vs Value Mid | M minus AY |
| BA | Tax Rate @ Ask | AI divided by M |
| BB | Price/SqFt | M divided by U |

Never replace these with displayed values or include them in an ordinary whole-row
update. Preserve formatting, validation and notes; do not change them while updating
research values. Plan helper writes only mapped/explicit cells in B:AX; A is identity.

## A genuinely new Sheet row

Do not append merely because a bounded search found nothing. Verify all populated IDs
and address/listing identity first. For a genuinely new completed evaluation, choose a
stable unique Property ID and save it in the repo record. Inspect a suitable existing
row's formulas, formatting and validation, then use connected Sheets tools to prepare
the new row without copying another property's data. Adapt formula row references,
write reviewed A:AX values, and verify ID uniqueness plus AY:BB formulas/outputs.
The preview helper deliberately supports existing rows only; a new-row operation is
explicit reviewed work, never an automatic fallback. Do not sync draft placeholders.

## Failure handling

If Sheets is unavailable, finish and publish the useful evaluation, preserve the
prepared update privately, and report that the Sheet write is blocked. Do not claim
success or create a duplicate row/replacement spreadsheet. Resume after a fresh read.
