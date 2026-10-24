"""Prepare, never execute, an existing-row update from a fresh Sheet snapshot."""
import argparse
import json
import math
from pathlib import Path
from .build_site import ROOT
from .research_io import now, write_json
from .validate import private_content


def cell_value(value):
    if isinstance(value, bool):
        return {'boolValue':value}
    if isinstance(value,(int,float)) and math.isfinite(value):
        return {'numberValue':value}
    if isinstance(value,str):
        return {'stringValue':value}  # Never interpret user text as a formula.
    raise ValueError('Patch values must be finite numbers, booleans or strings; null clearing is not automatic')


def plan(config, snapshot, record, patch=None, profile=None):
    if record.get('research_status') == 'draft':
        raise ValueError('Draft evaluations cannot be synced as completed research')
    if snapshot.get('spreadsheet_id') != config['spreadsheet_id'] or snapshot.get('sheet_name') != config['properties_tab']:
        raise ValueError('Snapshot spreadsheet/tab mismatch')
    if snapshot.get('headers') != config['headers']:
        raise ValueError('Live headers changed; refresh mapping before writing')
    start = snapshot.get('start_row')
    if not isinstance(start,int) or start < 2:
        raise ValueError('Snapshot start_row must be a 1-based data row (>=2)')
    property_id = record.get('master_database_id')
    if not isinstance(property_id,str) or not property_id.strip():
        raise ValueError('Record needs a verified master_database_id; never infer legacy IDs from slug')
    matches=[(start+i,row) for i,row in enumerate(snapshot['rows']) if row and str(row[0]).strip().casefold()==property_id.strip().casefold()]
    if len(matches)!=1:
        raise ValueError(f'Matched {len(matches)} rows in this snapshot; do not append/guess. Verify the ID column over the full populated range.')
    row_number, row = matches[0]
    updates={}
    for header, field in config['field_mapping'].items():
        value=record
        for key in field.split('.'):
            value=value.get(key) if isinstance(value,dict) else None
        if value is not None:
            updates[header]=value
    updates.update(patch or {})
    requests, changes = [], []
    for header,value in updates.items():
        if header not in config['writable_headers']:
            raise ValueError(f'Column is not writable: {header}')
        index=config['headers'].index(header)
        entered=cell_value(value)
        before=row[index] if index<len(row) else ''
        if value==before:
            continue
        if profile and private_content(json.dumps(value),profile):
            raise ValueError('Private destination detected in proposed Sheet summary')
        changes.append({'header':header,'column_index':index,'before':before,'after':value})
        requests.append({'updateCells':{'range':{'sheetId':config['properties_sheet_id'],
            'startRowIndex':row_number-1,'endRowIndex':row_number,'startColumnIndex':index,'endColumnIndex':index+1},
            'rows':[{'values':[{'userEnteredValue':entered}]}],'fields':'userEnteredValue'}})
    return {'schema_version':1,'prepared_at':now(),'mode':'preview_only',
            'spreadsheet_id':config['spreadsheet_id'],'sheet_name':config['properties_tab'],
            'property_id':property_id,'row_number':row_number,'changes':changes,
            'preconditions':{'headers':config['headers'],'property_id_cell':row[0],
                             'before_cells':{str(c['column_index']):c['before'] for c in changes},
                             'require_global_unique_id_check':True,
                             'note':'Snapshot is not an atomic lock. Re-read headers, full populated ID column and target before-values immediately before connector write; stop/replan on drift.'},
            'connector_arguments':{'spreadsheet_id':config['spreadsheet_id'],'requests':requests},
            'preserved_columns':config['formula_headers'],
            'next':'Review preview; verify live preconditions; apply via connected Sheets tool; read back values and formulas. No write was executed.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record',required=True)
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--patch',help='Optional reviewed {Sheet header: value} JSON; null clearing rejected')
    parser.add_argument('--config',default=str(ROOT/'config/master_sheet.json'))
    parser.add_argument('--profile',default=str(ROOT/'buyer_profile.json'))
    parser.add_argument('--out',required=True,help='Save under ignored private/; this is a preview, not a Sheet write')
    args=parser.parse_args()
    load=lambda path:json.loads(Path(path).read_text())
    result=plan(load(args.config),load(args.snapshot),load(args.record),load(args.patch) if args.patch else None,load(args.profile))
    write_json(args.out,result)
    print(json.dumps({'mode':result['mode'],'row':result['row_number'],'changed_cells':len(result['changes']),'out':args.out},indent=2))


if __name__=='__main__':
    main()
