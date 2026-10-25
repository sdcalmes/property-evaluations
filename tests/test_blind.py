import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from property_eval import blind_valuation as blind
from property_eval.research_io import write_json
from property_eval.validate import validate_repo

ROOT=Path(__file__).resolve().parents[1]


def intake():
    return {'as_of':'2026-10-25','subject':{'market_area':'Example municipality, suburban neighborhood',
        'property_type':'Two story','year_built':1998,'above_grade_sqft':2400,'exclusive_lot_acres':1,
        'garage_spaces':3,'condition':{'kitchen':'Painted original cabinets; functional layout; dates unknown'},
        'features':['Main floor suite'],'limitations':['No basement moisture inspection'],
        'prior_sales':[{'sale_date':'2011-01-01','sale_price':350000}]},
        'comps':[{'comp_id':'C1','market_area':'Same fictional neighborhood','sale_date':'2026-06-12',
                  'sale_price':750000,'above_grade_sqft':2450,'condition':{'overall':'Listing claims replacement roof; not inspected'}},
                 {'comp_id':'C2','market_area':'Nearby fictional neighborhood','sale_date':'2026-08-26',
                  'sale_price':725000,'above_grade_sqft':2350}], 'images':[]}


def result(packet,status='valued'):
    return {'run_id':packet['run_id'],'packet_sha256':blind.sha(packet),'status':status,
        'subject_asking_price_exposed':False,'other_exposure':[],'tools_used':['provided_packet'],
        'value_low':710000 if status=='valued' else None,'value_mid':735000 if status=='valued' else None,
        'value_high':755000 if status=='valued' else None,'confidence':'low' if status=='valued' else 'not_applicable',
        'comp_analysis':[{'comp_id':'C1','weight':.6,'adjusted_value':None,'reasoning':'Similar age and size; claimed roof update is uncertain.'},
                         {'comp_id':'C2','weight':.4,'adjusted_value':None,'reasoning':'Somewhat smaller; location differences uncertain.'}],
        'rationale':'Sold evidence supports a cautious interval; condition is incompletely documented.',
        'assumptions':['Ordinary inspection results'],'missing_evidence':['System replacement dates']}


class BlindTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'data/properties').mkdir(parents=True)
        (self.root/'evaluations').mkdir()
        shutil.copy(ROOT/'buyer_profile.json',self.root/'buyer_profile.json')
        self.record={'slug':'example','address':'123 Example Ln, WI','parcel_id':'TEST1','current_list_price':765000,
            'original_list_price':765000,'estimated_value_low':710000,'estimated_value_high':755000,
            'above_grade_sqft':2400,'evaluation_markdown':'example.md'}
        write_json(self.root/'data/properties/example.json',self.record)
        (self.root/'evaluations/example.md').write_text('# Fictional test property')

    def prepared(self):
        folder=blind.prepare(self.root,'example',intake(),True)
        packet=json.loads((folder/'packet.json').read_text())
        return folder,packet

    def test_allowlist_price_cues_and_source_urls_rejected(self):
        for mutate in [lambda d:d['subject'].update(current_list_price=765000),
                       lambda d:d['subject'].update(land='Bargain with an asking price of 765k'),
                       lambda d:d['subject'].update(land='Previously estimated at 765000'),
                       lambda d:d['comps'][0].update(listing_url='https://example.org'),
                       lambda d:d['subject'].update(features=['See https://example.org/listing']),
                       lambda d:d['subject'].update(features=['Only $765,000']),
                       lambda d:d['comps'][0].update(sale_date='2027-01-01')]:
            data=intake();mutate(data)
            with self.assertRaises(ValueError):blind.prepare(self.root,'example',data,True)
        with self.assertRaises(ValueError):blind.prepare(self.root,'example',intake())

    def test_completed_sale_equal_to_subject_ask_is_preserved(self):
        data=intake();data['comps'][0]['sale_price']=765000
        folder=blind.prepare(self.root,'example',data,True)
        packet=json.loads((folder/'packet.json').read_text())
        self.assertEqual(packet['comps'][0]['sale_price'],765000)
        self.assertNotIn('current_list_price',packet['subject'])
        self.assertEqual(packet['subject']['prior_sales'][0]['sale_price'],350000)

    def test_anonymous_images_have_hashes_and_comp_associations(self):
        source=self.root/'marketing-765000.jpg';Image.new('RGB',(120,80),'blue').save(source)
        data=intake();data['images']=[{'path':str(source),'price_overlay_checked':True,'property_id':'C1'}]
        folder=blind.prepare(self.root,'example',data,True)
        packet,meta=blind.verify_run(folder)
        self.assertEqual(packet['images'][0]['property_id'],'C1')
        self.assertEqual(packet['images'][0]['file'],'I01.jpg')
        self.assertNotIn('marketing-',(folder/'handoff.txt').read_text())
        with Image.open(folder/'I01.jpg') as image:self.assertFalse(image.getexif())
        (folder/'I01.jpg').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Image changed'):blind.verify_run(folder)
        data['images'][0]['price_overlay_checked']=False
        with self.assertRaisesRegex(ValueError,'Inspect every image'):blind.prepare(self.root,'example',data,True)

    def test_lock_compare_public_audit_and_no_valuation_overwrite(self):
        folder,packet=self.prepared();answer=result(packet)
        with self.assertRaises(FileNotFoundError):blind.compare(self.root,folder)
        with self.assertRaisesRegex(ValueError,'fresh subagent'):blind.lock(folder,answer,'agent-test')
        receipt=blind.lock(folder,answer,'agent-test',True,True)
        self.assertEqual(receipt['method'],'work_subagent_packet_only')
        with self.assertRaisesRegex(ValueError,'already locked'):blind.lock(folder,answer,'other',True,True)
        comparison=blind.compare(self.root,folder)
        self.assertEqual(comparison['difference_from_mid'],30000)
        public=blind.public_audit(self.root,folder,True)
        saved=json.loads((self.root/'data/properties/example.json').read_text())
        self.assertEqual(saved['estimated_value_low'],710000)
        self.assertEqual(saved['blind_valuation']['status'],'valued')
        self.assertFalse(blind.check_record(self.root,saved))
        audit=json.loads(public.read_text());audit['result']['value_mid']=740000;public.write_text(json.dumps(audit))
        self.assertTrue(any('hash mismatch' in e for e in blind.check_record(self.root,saved)))

    def test_packet_edit_and_subject_change_invalidate(self):
        folder,packet=self.prepared()
        data=copy.deepcopy(packet);data['subject']['beds']=4;write_json(folder/'packet.json',data)
        with self.assertRaisesRegex(ValueError,'changed after preparation'):blind.verify_run(folder)
        folder,packet=self.prepared();blind.lock(folder,result(packet),'agent-test',True,True)
        self.record['above_grade_sqft']=3000;write_json(self.root/'data/properties/example.json',self.record)
        with self.assertRaisesRegex(ValueError,'Subject facts changed'):blind.compare(self.root,folder)

    def test_contamination_insufficient_and_bad_result_rejected(self):
        _,packet=self.prepared()
        for change in [dict(subject_asking_price_exposed=True),dict(other_exposure=['Previous report']),
                       dict(tools_used=['web_search']),dict(value_low=800000),dict(packet_sha256='wrong'),
                       dict(rationale='The asking price justifies this range.'),dict(comp_analysis=[]),dict(value_mid=float('nan'))]:
            data=result(packet);data.update(change)
            with self.assertRaises(ValueError):blind.validate_result(data,packet)
        data=result(packet,'contaminated');data['subject_asking_price_exposed']=True
        data['rationale']='Subject asking price encountered; no independent estimate claimed.'
        blind.validate_result(data,packet)
        data=result(packet,'insufficient_evidence');blind.validate_result(data,packet)
        data['missing_evidence']=[]
        with self.assertRaises(ValueError):blind.validate_result(data,packet)

    def test_pending_unavailable_and_revision_rules(self):
        record={**self.record,'blind_valuation':{'method':blind.METHOD,'status':'pending'}}
        self.assertTrue(blind.check_record(self.root,record))
        record['research_status']='draft';self.assertFalse(blind.check_record(self.root,record))
        record['blind_valuation']={'method':blind.METHOD,'status':'unavailable','reason':'No fresh context handoff supported'}
        self.assertFalse(blind.check_record(self.root,record))
        folder,packet=self.prepared();blind.lock(folder,result(packet),'agent-test',True,True);blind.public_audit(self.root,folder,True)
        record=json.loads((self.root/'data/properties/example.json').read_text());record['estimated_value_high']=780000
        self.assertTrue(any('Final range differs' in e for e in blind.check_record(self.root,record)))
        record['valuation_revision']={'reason':'Documented change in condition','new_evidence':['Verified repair scope'], 'original_run_id':packet['run_id']}
        self.assertFalse(blind.check_record(self.root,record))

    def test_property_page_discloses_method_and_links_audit(self):
        from property_eval.build_site import build
        for folder in ('templates','static'):(self.root/folder).mkdir()
        for name in ('templates/index.html','templates/property.html','static/style.css'):
            shutil.copy(ROOT/name,self.root/name)
        folder,packet=self.prepared();blind.lock(folder,result(packet),'agent-test',True,True)
        blind.public_audit(self.root,folder,True)
        output=build(self.root)
        text=(output/'properties/example/index.html').read_text()
        self.assertIn('Independent valuation pass',text)
        self.assertIn('Recorded valuation audit',text)
        self.assertIn('not access-isolated',text)

    def test_legacy_records_remain_nonblind_and_valid(self):
        self.assertFalse(blind.check_record(self.root,self.record))
        self.assertFalse(validate_repo(self.root)[0]['errors'])


if __name__=='__main__':unittest.main()
