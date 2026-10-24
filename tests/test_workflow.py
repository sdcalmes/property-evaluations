import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from property_eval import evidence, routing, research
from property_eval.validate import check, validate_repo
from property_eval.research_io import write_json

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT/'buyer_profile.json').read_text())


class EvidenceTests(unittest.TestCase):
    def test_append_idempotent_dates_conflicts_and_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=evidence.Ledger(Path(temp)/'evidence.json','example')
            first=evidence.observation('listing.price',500000,'https://example.org/1','2026-10-20','listing_claim','listing')
            ledger.add(first);ledger.add(first)
            ledger.add(evidence.observation('listing.price',490000,'https://example.org/2','2026-10-24','listing_claim','listing'))
            ledger.add(evidence.observation('shed.permission',None,None,'2026-10-24','unknown','document'))
            report=ledger.report('2026-10-24T12:00:00Z')
            self.assertEqual(report['observation_count'],3)
            self.assertEqual(len(report['conflicts']),1)
            self.assertEqual(len(report['stale']),1)
            self.assertEqual(report['unknown_facts'],['shed.permission'])
            self.assertEqual(ledger.data['observations'][0]['observed_at'],'2026-10-20')
            ledger.data['observations'][0]['value']=10
            self.assertIn('hash mismatch',ledger.report('2026-10-24')['invalid'][0]['error'])

    def test_invalid_source_unknown_and_time(self):
        with self.assertRaises(ValueError):
            evidence.observation('x',1,None,'2026-10-24','official_record','tax')
        with self.assertRaises(ValueError):
            evidence.observation('x',True,None,'2026-10-24','unknown','document')
        with self.assertRaises(ValueError):
            evidence.timestamp('2026-10-24T12:00:00')
        with tempfile.TemporaryDirectory() as temp:
            ledger=evidence.Ledger(Path(temp)/'x.json','x')
            ledger.add(evidence.observation('x',1,'https://example.org','2026-10-25','listing_claim','listing'))
            self.assertTrue(ledger.report('2026-10-24')['invalid'])


class ValidationTests(unittest.TestCase):
    def record(self):
        return {'slug':'example','ratings':{'kitchen':8},'buyer_fit_score':8,'score_weight_coverage_percent':16,
                'estimated_value_low':400000,'estimated_value_high':500000,'caution_price':490000,'walk_away_price':500000}

    def test_score_range_workshop_and_private_fields(self):
        record=self.record();self.assertFalse(check(record,PROFILE)['errors'])
        record.update(buyer_fit_score=9,opening_offer='$500,000–$400,000',storage_fit={'subdivision':True,'large_workshop_required':True},commutes=[{'address':'private'}])
        result=check(record,PROFILE)
        self.assertEqual(len(result['errors']),4)
        record['ratings']['kitchen']=float('nan')
        self.assertTrue(any('finite' in e for e in check(record,PROFILE)['errors']))

    def test_privacy_and_traffic_mismatch_are_flagged(self):
        profile=copy.deepcopy(PROFILE)
        profile['destinations']['lisa_work']['routing_address']='123 Secret Lane, Example, WI'
        record=self.record();record['notes']='123%20Secret%20Lane'
        record['commutes']=[{'destination':'Work','traffic_aware':True}]
        result=check(record,profile)
        self.assertTrue(any('Private' in e for e in result['errors']))
        self.assertTrue(any('traffic' in e for e in result['warnings']))


class RoutingTests(unittest.TestCase):
    def test_traffic_is_not_compared_with_static_baseline(self):
        profile={'destinations':{'work':{'label':'Work','routing_address':'Private destination','baseline_no_traffic_minutes':31}}}
        route={'duration_minutes':45,'static_duration_minutes':25,'distance_miles':22,'provider':'google','traffic_aware':True}
        with patch('property_eval.routing.route_google',return_value=route):
            row=routing.evaluate('Subject',profile,'google','unused')[0]
        self.assertEqual(row['candidate_minutes'],45)
        self.assertEqual(row['static_candidate_minutes'],25)
        self.assertEqual(row['delta_minutes'],-6)
        self.assertEqual(row['comparison_basis'],'static_to_static')
        self.assertNotIn('Private destination',json.dumps(row))
        route['static_duration_minutes']=None
        with patch('property_eval.routing.route_google',return_value=route):
            row=routing.evaluate('Subject',profile,'google','unused')[0]
        self.assertIsNone(row['delta_minutes'])
        self.assertEqual(row['comparison_basis'],'unavailable')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('data/properties','evaluations','research/example'):
            (self.root/name).mkdir(parents=True)
        write_json(self.root/'buyer_profile.json',PROFILE)
        self.record={'slug':'example','address':'123 Example Ln, WI','parcel_id':'EXAMPLE1',
                     'listing_url':'https://example.org/listing','evaluation_markdown':'example.md',
                     'ratings':{'kitchen':8},'buyer_fit_score':8,'score_weight_coverage_percent':16}
        write_json(self.root/'data/properties/example.json',self.record)
        (self.root/'evaluations/example.md').write_text('# Existing reviewed evaluation\n')

    def invoke(self,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return research.run(self.root,'example',**kwargs)

    def test_identity_no_duplicate_creation(self):
        for target in ('example','EXAMPLE1','123 Example Ln, WI','https://example.org/listing?tracking=1'):
            self.assertEqual(research.resolve_target(self.root,target)['slug'],'example')
        with self.assertRaisesRegex(ValueError,'0 existing'):
            research.resolve_target(self.root,'https://example.org/new')
        self.assertEqual(len(list((self.root/'data/properties').glob('*.json'))),1)
        other={**self.record,'slug':'duplicate','evaluation_markdown':'duplicate.md'}
        write_json(self.root/'data/properties/duplicate.json',other)
        (self.root/'evaluations/duplicate.md').write_text('# Duplicate')
        self.assertTrue(any('Duplicate' in e for e in validate_repo(self.root)[0]['errors']))

    def test_missing_config_partial_and_no_production_changes(self):
        before=(self.root/'data/properties/example.json').read_bytes()
        result=self.invoke(offline=True)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['steps']['gis']['status'],'blocked')
        self.assertEqual(result['steps']['routes']['status'],'blocked')
        self.assertEqual((self.root/'data/properties/example.json').read_bytes(),before)
        self.assertTrue((self.root/'private/research/example/checklist.md').exists())

    def test_resume_hashes_and_checks_freshness(self):
        write_json(self.root/'research/example/gis.json',{'parcel_id':'EXAMPLE1','units':'feet'})
        data={'parcel_id':'EXAMPLE1','sources':[{'source_url':'https://example.org/gis','captured_at':'2026-10-24'}],'layers':{},'errors':{}}
        with patch('property_eval.gis.capture',return_value=data) as capture:
            first=self.invoke(steps=['gis','checks'])
            second=self.invoke(steps=['gis','checks'])
            self.assertEqual(capture.call_count,1)
        self.assertTrue(second['steps']['gis']['reused'])
        self.assertFalse(second['steps']['checks']['reused'])
        with patch('property_eval.gis.capture') as capture:
            result=self.invoke(steps=['gis'],offline=True)
            capture.assert_not_called()
            self.assertTrue(result['steps']['gis']['reused'])
        bundle=self.root/'private/research/example/gis-bundle.json'
        bundle.write_text('{}')
        result=self.invoke(steps=['gis'],offline=True)
        self.assertEqual(result['steps']['gis']['status'],'blocked')

    def test_photo_resume_requires_every_image_and_contact_sheet(self):
        from PIL import Image
        write_json(self.root/'research/example/photos.json',{'images':[{'src':'https://example.org/image.jpg'}]})
        buffer=io.BytesIO();Image.new('RGB',(1000,700),'red').save(buffer,format='JPEG')
        with patch('property_eval.photos.fetch_bytes',return_value=(buffer.getvalue(),'image/jpeg')) as fetch:
            first=self.invoke(steps=['photos'])
            self.assertEqual(first['steps']['photos']['status'],'complete')
            second=self.invoke(steps=['photos'],offline=True)
            self.assertTrue(second['steps']['photos']['reused'])
            self.assertEqual(fetch.call_count,1)
        folder=self.root/'private/research/example/photos'
        (folder/'contact-01.jpg').unlink()
        result=self.invoke(steps=['photos'],offline=True)
        self.assertEqual(result['steps']['photos']['status'],'blocked')
        with patch('property_eval.photos.fetch_bytes') as fetch:
            result=self.invoke(steps=['photos'])
            fetch.assert_not_called()
        self.assertTrue((folder/'contact-01.jpg').exists())
        self.assertEqual(result['steps']['photos']['status'],'complete')

    def test_failed_refresh_does_not_map_stale_bundle(self):
        write_json(self.root/'research/example/gis.json',{'parcel_id':'EXAMPLE1','units':'feet'})
        write_json(self.root/'research/example/map.json',{})
        write_json(self.root/'private/research/example/gis-bundle.json',{'old':'capture'})
        with patch('property_eval.gis.capture',side_effect=RuntimeError('HTTP 403')),patch('property_eval.parcel_map.render') as render:
            result=self.invoke(steps=['gis','map'],refresh=True)
            render.assert_not_called()
        self.assertEqual(result['steps']['map']['status'],'blocked')

    def test_partial_layer_failure_is_not_success(self):
        write_json(self.root/'research/example/gis.json',{'parcel_id':'EXAMPLE1','units':'feet'})
        with patch('property_eval.gis.capture',return_value={'parcel_id':'EXAMPLE1','sources':[],'errors':{'wetland':'blocked'}}):
            result=self.invoke(steps=['gis'])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['steps']['gis']['status'],'partial')


if __name__=='__main__':
    unittest.main()
