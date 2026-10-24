import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from property_eval.initialize import initialize
from property_eval.evidence import Ledger, observation
from property_eval.evidence_public import export, validate_summary
from property_eval.sheet_plan import plan
from property_eval.build_site import build
from property_eval.validate import validate_repo
from property_eval.research import run

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'config/master_sheet.json').read_text())


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for folder in ('evaluations','templates','static','data/properties'):
            (self.root/folder).mkdir(parents=True)
        for name in ('buyer_profile.json','evaluations/TEMPLATE.md','templates/index.html','templates/property.html','static/style.css'):
            shutil.copy(ROOT/name,self.root/name)
        self.profile=json.loads((self.root/'buyer_profile.json').read_text())

    def create(self):
        return initialize(self.root,'123 Example Lane, Sample, WI','https://example.org/listing','P123')


class InitializationTests(ProjectFixture):
    def test_draft_unknowns_and_dashboard_exclusion(self):
        record=self.create()
        self.assertEqual(record['research_status'],'draft')
        self.assertIsNone(record['current_list_price'])
        self.assertIsNone(record['evaluation_date'])
        self.assertTrue(all(v is None for v in record['ratings'].values()))
        self.assertTrue((self.root/'research/123-example-lane/gis.draft.json').exists())
        self.assertFalse((self.root/'research/123-example-lane/gis.json').exists())
        output=build(self.root)
        self.assertIn('No evaluations saved yet',(output/'index.html').read_text())
        self.assertFalse((output/'properties/123-example-lane').exists())
        self.assertFalse(validate_repo(self.root)[0]['errors'])

    def test_duplicate_checks_and_no_overwrite(self):
        record=self.create()
        original=(self.root/'data/properties/123-example-lane.json').read_bytes()
        for args in [dict(address='123 Example Ln, Another postal name, WI',slug='another'),
                     dict(address='456 Other Rd',parcel_id='P-123'),
                     dict(address='456 Other Rd',listing_url='https://example.org/listing?tracking=1')]:
            with self.assertRaisesRegex(ValueError,'existing property'):
                initialize(self.root,**args)
        self.assertEqual(original,(self.root/'data/properties/123-example-lane.json').read_bytes())
        self.assertEqual(len(list((self.root/'data/properties').glob('*.json'))),1)
        with self.assertRaisesRegex(ValueError,'Invalid slug'):
            initialize(self.root,'456 Other Rd',slug='../escape')

    def test_orphan_research_not_overwritten_and_promotion_checked(self):
        (self.root/'research/orphan').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'output already exists'):
            initialize(self.root,'456 Other Rd',slug='orphan')
        record=self.create();record['research_status']='reviewed'
        (self.root/'data/properties/123-example-lane.json').write_text(json.dumps(record))
        self.assertTrue(any('placeholder' in error for error in validate_repo(self.root)[0]['errors']))


class PublicEvidenceTests(ProjectFixture):
    def setUp(self):
        super().setUp();self.record=self.create();self.slug=self.record['slug']
        self.ledger=Ledger(self.root/'private/evidence.json',self.slug)

    def item(self,**changes):
        values=dict(fact='listing.status',value='Active',source_url='https://example.org/listing',
                    observed_at='2020-01-01',basis='listing_claim',kind='listing')
        values.update(changes)
        item=observation(**values);self.ledger.add(item)
        return item

    def test_explicit_review_selection_and_dates(self):
        item=self.item()
        with self.assertRaisesRegex(ValueError,'explicitly attest'):
            export(self.root,self.slug,self.ledger.path,[item['id']])
        path=export(self.root,self.slug,self.ledger.path,[item['id']],True)
        self.assertEqual(json.loads(path.read_text())['observations'][0]['observed_at'],'2020-01-01')
        export(self.root,self.slug,self.ledger.path,[item['id']],True)
        self.assertEqual(len(json.loads(path.read_text())['observations']),1)
        second=self.item(value='Sold',observed_at='2020-02-01')
        export(self.root,self.slug,self.ledger.path,[second['id']],True)
        ledger=validate_summary(path,self.slug,self.profile)
        self.assertEqual(len(ledger.data['observations']),2)
        self.assertTrue(ledger.report()['conflicts'])

    def test_private_raw_and_signed_urls_rejected_before_write(self):
        for changes in [dict(fact='raw.owner_data'),dict(basis='source_capture'),
                        dict(source_url='https://example.org/?token=secret'),
                        dict(source_url='https://maps.google.com/maps/dir/A/B'),
                        dict(value={'routing_address':'Some private address'})]:
            item=self.item(**changes)
            with self.assertRaises(ValueError):
                export(self.root,self.slug,self.ledger.path,[item['id']],True)
        self.assertFalse((self.root/'data/evidence'/f'{self.slug}.json').exists())

    def test_new_session_import_and_default_validation(self):
        item=self.item();export(self.root,self.slug,self.ledger.path,[item['id']],True)
        with contextlib.redirect_stdout(io.StringIO()):
            result=run(self.root,self.slug,steps=['checks'],offline=True)
        copied=Ledger(self.root/'private/research'/self.slug/'evidence.json',self.slug)
        self.assertEqual(copied.data['observations'][0]['id'],item['id'])
        self.assertFalse(validate_repo(self.root)[0]['errors'])
        self.assertTrue(any('Stale evidence' in warning for warning in validate_repo(self.root)[0]['warnings']))
        public=self.root/'data/evidence'/f'{self.slug}.json'
        data=json.loads(public.read_text());data['observations'][0]['value']='tampered';public.write_text(json.dumps(data))
        self.assertTrue(any('Public evidence' in error for error in validate_repo(self.root)[0]['errors']))


class SheetPlanTests(unittest.TestCase):
    def setUp(self):
        self.row=['']*54;self.row[0]='EXAMPLE-ID';self.row[12]=500000
        self.snapshot={'spreadsheet_id':CONFIG['spreadsheet_id'],'sheet_name':'Properties','start_row':9,
                       'headers':CONFIG['headers'],'rows':[self.row]}
        self.record={'master_database_id':'EXAMPLE-ID','current_list_price':490000,'annual_taxes':None,'research_status':'reviewed'}

    def test_existing_row_sparse_updates_preserve_formulas_and_unknowns(self):
        result=plan(CONFIG,self.snapshot,self.record,{'Shed':'=not a formula'})
        self.assertEqual(result['row_number'],9)
        self.assertEqual(result['mode'],'preview_only')
        self.assertEqual(len(result['changes']),2)
        self.assertNotIn('Property Taxes',[c['header'] for c in result['changes']])
        for req in result['connector_arguments']['requests']:
            self.assertLess(req['updateCells']['range']['startColumnIndex'],50)
            self.assertEqual(req['updateCells']['fields'],'userEnteredValue')
        self.assertEqual(result['connector_arguments']['requests'][1]['updateCells']['rows'][0]['values'][0]['userEnteredValue'],{'stringValue':'=not a formula'})

    def test_identity_header_formula_and_draft_failures(self):
        for patch in ({'Value Mid':1},{'Property ID':'new'},{'Property Taxes':None}):
            with self.assertRaises(ValueError):plan(CONFIG,self.snapshot,self.record,patch)
        for rows in ([],[self.row,self.row]):
            snapshot={**self.snapshot,'rows':rows}
            with self.assertRaisesRegex(ValueError,'Matched'):
                plan(CONFIG,snapshot,self.record)
        snapshot=copy.deepcopy(self.snapshot);snapshot['headers'][1]='Changed'
        with self.assertRaisesRegex(ValueError,'headers changed'):plan(CONFIG,snapshot,self.record)
        with self.assertRaisesRegex(ValueError,'Draft'):plan(CONFIG,self.snapshot,{**self.record,'research_status':'draft'})
        with self.assertRaisesRegex(ValueError,'verified master_database_id'):plan(CONFIG,self.snapshot,{})


if __name__=='__main__':unittest.main()
