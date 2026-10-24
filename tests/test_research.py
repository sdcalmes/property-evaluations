"""Offline regression tests: no dependency on live listings or county availability."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from property_eval.gis import query_layer, capture
from property_eval.research_io import JSONCapture
from property_eval.photos import discover, download, review
from property_eval.parcel_map import esri_polygon, render


class CaptureTests(unittest.TestCase):
    def test_cached_provenance_survives_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('property_eval.research_io.fetch_bytes', return_value=(b'{"objectIds":[]}', 'application/json')) as fetch:
                first = JSONCapture(directory)
                first.get('https://example.org/query', {'f':'json'})
                second = JSONCapture(directory)
                self.assertEqual(second.get('https://example.org/query', {'f':'json'}), {'objectIds':[]})
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(first.sources, second.sources)

    def test_api_error_not_cached_and_pending_request_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('property_eval.research_io.fetch_bytes', return_value=(b'{"error":{"code":403}}', 'application/json')):
                with self.assertRaisesRegex(ValueError, 'API error'):
                    JSONCapture(directory).get('https://example.org/query')
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 1)
            self.assertTrue((Path(directory)/'pending-request.json').exists())

    def test_batched_query_and_truncation_rejected(self):
        class Client:
            calls = []
            truncate = False
            def get(self, endpoint, params):
                self.calls.append(params)
                if 'returnIdsOnly' in params:
                    return {'objectIds': list(range(205))}
                result = {'features': [{'attributes':{'OBJECTID':int(x)}} for x in params['objectIds'].split(',')]}
                if self.truncate:
                    result['exceededTransferLimit'] = True
                return result
        client = Client()
        self.assertEqual(len(query_layer(client, 'https://example.org/2', {'outSR':6609})['features']),205)
        self.assertEqual(len(client.calls),4)
        client.truncate = True
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            query_layer(client, 'https://example.org/2', {'outSR':6609})

    def test_failed_layer_is_not_empty_constraint(self):
        class Client:
            sources = []
        polygon={'features':[{'geometry':{'rings':[[[0,0],[100,0],[100,100],[0,100],[0,0]]]}}]}
        config={'parcel_id':"A'B",'parcel_layer':'https://example.org/2','spatial_reference':6609,
                'units':'feet','layers':{'wetlands':{'url':'https://example.org/3'}}}
        with patch('property_eval.gis.query_layer', side_effect=[polygon,RuntimeError('HTTP 403')]) as query:
            result=capture(config,Client())
        self.assertIn('wetlands',result['errors'])
        self.assertNotIn('wetlands',result['layers'])
        self.assertEqual(query.call_args_list[0].args[2]['where'], "TAXKEY = 'A''B'")


class PhotoTests(unittest.TestCase):
    def test_lazy_srcset_jsonld_and_url_dedup(self):
        html='''<img src="placeholder.gif" data-src="/one.webp" alt="Kitchen">
        <img srcset="/two-small.jpg 400w, /two-large.jpg 1600w">
        <script type="application/ld+json">{"image":["/one.webp",{"url":"/three.jpg"}]}</script>'''
        result=discover(html,'https://example.org/listing')
        self.assertEqual([x['src'] for x in result],['https://example.org/one.webp','https://example.org/two-large.jpg','https://example.org/three.jpg'])

    def test_validation_resume_thumbnails_and_review(self):
        from PIL import Image
        buffer=io.BytesIO();Image.new('RGB',(402,268),'blue').save(buffer,format='WEBP')
        manifest={'images':[{'src':'https://example.org/one.webp','alt':'Kitchen'}, {'src':'https://example.org/blocked.jpg'}]}
        with tempfile.TemporaryDirectory() as directory:
            with patch('property_eval.photos.fetch_bytes',side_effect=[(buffer.getvalue(),'image/webp'),(b'<html>Forbidden</html>','text/html')]):
                result=download(manifest,directory)
            self.assertTrue(result[0]['thumbnail_only'])
            self.assertEqual(result[1]['status'],'failed')
            with patch('property_eval.photos.fetch_bytes') as fetch:
                again=download({'images':manifest['images'][:1]},directory)
                fetch.assert_not_called()
            self.assertEqual(result[0]['captured_at'],again[0]['captured_at'])
            review(directory)
            self.assertTrue((Path(directory)/'contact-01.jpg').exists())
            self.assertIn('Kitchen',(Path(directory)/'review.html').read_text())


class MapTests(unittest.TestCase):
    def test_multipart_and_hole_not_first_ring_only(self):
        outer=[[0,0],[100,0],[100,100],[0,100],[0,0]]
        hole=[[20,20],[40,20],[40,40],[20,40],[20,20]]
        island=[[200,0],[210,0],[210,10],[200,10],[200,0]]
        self.assertAlmostEqual(esri_polygon({'rings':[outer,hole,island]}).area,9700)

    def test_map_geometry_does_not_approve_building(self):
        parcel={'features':[{'geometry':{'rings':[[[0,0],[100,0],[100,100],[0,100],[0,0]]]}}]}
        bundle={'units':'feet','spatial_reference':6609,'parcel':parcel,'layers':{},'errors':{'wetlands':'Unavailable'}}
        config={'title':'Test','spatial_reference':6609,'study_areas':[{'label':'Outside','kind':'shed','origin':[95,95],'width_ft':10,'depth_ft':12}]}
        with tempfile.TemporaryDirectory() as directory:
            result=render(bundle,config,Path(directory)/'map.png')
            self.assertTrue((Path(directory)/'map.png').exists())
        self.assertFalse(result['studies'][0]['inside_mapped_parcel'])
        self.assertFalse(result['studies'][0]['legally_approved'])
        self.assertIn('wetlands',result['layer_errors'])
        bundle['units']='degrees'
        with self.assertRaisesRegex(ValueError,'projected'):
            render(bundle,config,'unused.png')


class StoragePolicyTests(unittest.TestCase):
    def test_workshop_unavailable_does_not_reduce_subdivision_score(self):
        from property_eval.scoring import score
        profile=json.loads((Path(__file__).resolve().parents[1]/'buyer_profile.json').read_text())
        base={'ratings':{'garage_outbuilding':8},'storage_fit':{'subdivision':True,'larger_shed_potential':False}}
        result=score(base,profile)
        self.assertEqual(result['fit_score_0_to_10'],8)
        self.assertFalse(profile['requirements']['outbuilding_potential']['workshop_30x40_required'])
        self.assertEqual(profile['requirements']['garden']['minimum_clear_area_sqft'],1200)
        self.assertIn('No workshop penalty',result['garage_storage_guidance']['notes'])

    def test_browser_photo_import_and_invalid_zoning_are_audited(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source';source.mkdir()
            Image.new('RGB',(1000,700),'green').save(source/'001.jpg')
            with patch('property_eval.photos.fetch_bytes') as fetch:
                result=download({'images':[{'src':'https://example.org/gallery/1.jpg'}]},Path(directory)/'out',source,'2026-10-24T18:00:00Z')
                fetch.assert_not_called()
            self.assertEqual(result[0]['status'],'ok')
            self.assertFalse(result[0]['thumbnail_only'])
            self.assertEqual(result[0]['captured_at'],'2026-10-24T18:00:00Z')
        geometry={'rings':[[[0,0],[10,10],[0,10],[10,0],[0,0]]]}
        with self.assertRaisesRegex(ValueError,'Invalid GIS ring'):
            esri_polygon(geometry)
        repairs=[]
        self.assertEqual(esri_polygon(geometry,True,repairs).area,50)
        self.assertTrue(repairs)


if __name__ == '__main__':
    unittest.main()
