"""Capture one parcel and configured ArcGIS layers. python -m property_eval.gis --help"""
import argparse
import json
from pathlib import Path
from .research_io import JSONCapture, now, write_json


def query_layer(client, layer, params):
    """IDs first, bounded batches: no silent maxRecordCount truncation."""
    endpoint = layer.rstrip('/') + '/query'
    ids = client.get(endpoint, {'f': 'json', **params, 'returnIdsOnly': 'true', 'returnGeometry': 'false'})
    if ids.get('exceededTransferLimit') or 'objectIds' not in ids:
        raise ValueError('Object-ID query missing/truncated; narrow the search')
    object_ids = ids['objectIds'] or []
    combined = {'features': []}
    for start in range(0, len(object_ids), 100):
        batch = object_ids[start:start + 100]
        result = client.get(endpoint, {'f': 'json', 'objectIds': ','.join(map(str, batch)),
                                      'outFields': '*', 'returnGeometry': 'true', 'outSR': params['outSR']})
        if result.get('exceededTransferLimit') or len(result.get('features', [])) != len(batch):
            raise ValueError('Incomplete feature batch; narrow search or reduce batch size')
        if start == 0:
            combined.update({k: v for k, v in result.items() if k != 'features'})
        combined['features'].extend(result['features'])
    return combined


def capture(config, client):
    parcel_id = config['parcel_id']
    field = config.get('parcel_id_field', 'TAXKEY')
    if not field.replace('_', '').isalnum():
        raise ValueError('Invalid parcel field')
    sr = config['spatial_reference']
    parcel = query_layer(client, config['parcel_layer'], {
        'where': f"{field} = '{parcel_id.replace(chr(39), chr(39)*2)}'", 'outSR': sr})
    if len(parcel['features']) != 1:
        raise ValueError(f'Expected one parcel; got {len(parcel["features"])}')
    geometry = parcel['features'][0]['geometry']
    if not geometry.get('rings'):
        raise ValueError('Subject must have polygon geometry')
    geometry = {**geometry, 'spatialReference': {'wkid': sr}}
    coords = [xy for ring in geometry['rings'] for xy in ring]
    pad = config.get('neighbor_buffer_ft', 500)
    envelope = {'xmin': min(p[0] for p in coords) - pad, 'xmax': max(p[0] for p in coords) + pad,
                'ymin': min(p[1] for p in coords) - pad, 'ymax': max(p[1] for p in coords) + pad,
                'spatialReference': {'wkid': sr}}
    layers, errors = {}, {}
    for name, spec in config['layers'].items():
        area = envelope if spec.get('scope') == 'neighbors' else geometry
        try:
            layers[name] = query_layer(client, spec['url'], {
                'geometry': json.dumps(area, separators=(',', ':')),
                'geometryType': 'esriGeometryEnvelope' if area is envelope else 'esriGeometryPolygon',
                'inSR': sr, 'outSR': sr, 'spatialRel': 'esriSpatialRelIntersects'})
        except (ValueError, RuntimeError) as exc:
            errors[name] = str(exc)
    return {'schema_version': 1, 'assembled_at': now(), 'parcel_id': parcel_id,
            'spatial_reference': sr, 'units': config['units'], 'parcel': parcel,
            'layers': layers, 'errors': errors, 'sources': client.sources}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    parser.add_argument('--inspect', help='Discover a REST service/layer metadata URL')
    parser.add_argument('--out')
    parser.add_argument('--cache', default='private/research/cache')
    parser.add_argument('--refresh', action='store_true', help='Refetch; omit when importing browser responses')
    args = parser.parse_args()
    if args.inspect:
        metadata = JSONCapture(args.cache, args.refresh).get(args.inspect.rstrip('/'), {'f': 'json'})
        if args.out:
            write_json(args.out, metadata)
        print(json.dumps(metadata, indent=2))
        return
    if not args.config or not args.out:
        parser.error('--config and --out are required for parcel capture')
    config = json.loads(Path(args.config).read_text())
    if config.get('units') != 'feet':
        parser.error('Requires a projected CRS in feet; reproject before use')
    result = capture(config, JSONCapture(args.cache, args.refresh))
    write_json(args.out, result)
    print(json.dumps({'out': args.out, 'features': {k: len(v['features']) for k, v in result['layers'].items()}, 'errors': result['errors']}, indent=2))
    if result['errors']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
