"""Run/resume research for an existing record. Never changes production evaluations."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .build_site import ROOT, SLUG
from .research_io import JSONCapture, now, write_json
from .evidence import Ledger, observation
from .validate import validate_repo

MANUAL_CHECKS = [
    'Verify current listing status and price from a current source; do not infer from cached photos.',
    'Inspect every subject photo and strongest comp interiors; separate listing claims from visual observations.',
    'Prepare a neutral blind packet, delegate to a fresh no-history valuation subagent, lock its result before comparing the ask; disclose unavailable/contaminated passes.',
    'Verify actual garage dimensions and small garden shed permission; large workshop is optional.',
    'Verify 30×40 garden sun, grade, septic/reserve, fence rules and usable location.',
    'Obtain disclosure, survey/title/covenants, well/septic plans and documented improvement dates.',
    'Review evidence conflicts/freshness, update existing JSON/Markdown, then existing Sheet row by property ID.'
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_target(root, target):
    def normalized(value):
        if value.startswith(('http://', 'https://')):
            url = urlsplit(value)
            return (url.netloc.casefold() + url.path).rstrip('/')
        return re.sub(r'\s+', ' ', value.casefold()).strip()
    matches = []
    for path in (root / 'data/properties').glob('*.json'):
        record = json.loads(path.read_text())
        if any(normalized(target) == normalized(str(record.get(key) or '')) for key in ('slug', 'address', 'listing_url', 'parcel_id')):
            matches.append(record)
    if len(matches) != 1:
        raise ValueError(f'Target matched {len(matches)} existing records; use an exact existing slug, address, parcel ID or listing URL. No new record was created.')
    record = matches[0]
    if not SLUG.fullmatch(record['slug']):
        raise ValueError('Invalid property slug')
    return record


def run(root, target, steps=None, refresh=False, offline=False, provider='osrm', departure=None, profile_path=None):
    from . import gis, photos, parcel_map, routing
    root = Path(root).resolve()
    record = resolve_target(root, target)
    slug = record['slug']
    work = root / 'private/research' / slug
    work.mkdir(parents=True, exist_ok=True)
    config = root / 'research' / slug
    manifest_path = work / 'run.json'
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'slug': slug, 'steps': {}}
    if old.get('slug') != slug:
        raise ValueError('Run manifest identity mismatch')
    ledger = Ledger(work / 'evidence.json', slug)
    public_path = root / 'data/evidence' / (slug + '.json')
    if public_path.is_file():
        from .evidence_public import validate_summary
        public = validate_summary(public_path, slug, json.loads((root / 'buyer_profile.json').read_text()))
        for item in public.data['observations']:
            ledger.add(item)  # Idempotent; preserve dates, values and conflicts across sessions.
    manifest = {'schema_version': 1, 'slug': slug, 'started_at': now(), 'steps': dict(old['steps']),
                'manual_review_required': MANUAL_CHECKS}
    selected = steps or ['gis', 'photos', 'map', 'routes', 'blind', 'checks']
    if any(name not in ('gis', 'photos', 'map', 'routes', 'blind', 'checks') for name in selected):
        raise ValueError('Unknown research step')
    # Enforce dependency order regardless of command-line ordering.
    selected = [name for name in ('gis', 'photos', 'map', 'routes', 'blind', 'checks') if name in selected]
    current = {}

    def step(name, inputs, outputs, action, reason=None, network=False):
        fingerprint = hashlib.sha256(json.dumps({
            'inputs': {str(p.relative_to(root)) if p.is_relative_to(root) else str(p): digest(p) if p.is_file() else None for p in inputs},
            'provider': provider if name == 'routes' else None,
            'departure': departure if name == 'routes' else None,
            'toolkit': {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')}
        }, sort_keys=True).encode()).hexdigest()
        previous = old['steps'].get(name, {})
        if reason:
            result = {'status': 'blocked', 'reason': reason}
        elif name not in ('checks', 'blind') and not refresh and previous.get('status') == 'complete' and previous.get('fingerprint') == fingerprint and all(
                p.is_file() and previous.get('output_hashes', {}).get(str(p.relative_to(work))) == digest(p) for p in outputs) and all(
                    (work / name).is_file() and digest(work / name) == expected for name, expected in previous.get('output_hashes', {}).items()):
            result = {**previous, 'reused': True}
        elif offline and network:
            result = {'status': 'blocked', 'reason': 'Offline mode: no matching complete capture. Run online or import browser evidence first.'}
        else:
            started = now()
            try:
                detail = action() or {}
                result = {'status': detail.pop('status', 'complete'), 'started_at': started, 'completed_at': now(), 'detail': detail,
                          'fingerprint': fingerprint, 'reused': False,
                          'output_hashes': {str(p.relative_to(work)): digest(p) for p in outputs if p.is_file()}}
                if result['status'] == 'complete' and any(not p.is_file() for p in outputs):
                    result['status'] = 'failed'
                    result['reason'] = 'A declared output was not produced'
            except (OSError, ValueError, RuntimeError, KeyError, ImportError) as exc:
                result = {'status': 'failed', 'started_at': started, 'completed_at': now(), 'reason': str(exc)}
        current[name] = result
        manifest['steps'][name] = result
        write_json(manifest_path, manifest)
        print(f"{name}: {result['status']}" + (' (reused)' if result.get('reused') else ''), flush=True)
        return result

    bundle_path = work / 'gis-bundle.json'
    if 'gis' in selected:
        def get_gis():
            settings = json.loads((config / 'gis.json').read_text())
            if settings.get('units') != 'feet':
                raise ValueError('Configured GIS requires projected feet')
            if record.get('parcel_id') and settings['parcel_id'] != record['parcel_id']:
                raise ValueError('GIS config parcel does not match property record')
            data = gis.capture(settings, JSONCapture(work / 'cache', refresh))
            write_json(bundle_path, data)
            for source in data['sources']:
                ledger.add(observation('gis.capture', {'parcel_id': data['parcel_id']}, source['source_url'],
                                       source['captured_at'], 'official_record', 'gis', 'Raw mapped data; no legal buildability inference.'))
            return {'status': 'partial' if data['errors'] else 'complete', 'layer_errors': data['errors']}
        step('gis', [config / 'gis.json'], [bundle_path], get_gis,
             reason='Missing GIS config; see docs/research.md' if not (config / 'gis.json').is_file() else None, network=True)
    photos_path = work / 'photos'
    if 'photos' in selected:
        def get_photos():
            items = photos.download(json.loads((config / 'photos.json').read_text()), photos_path, refresh=refresh)
            photos.review(photos_path)
            for item in items:
                if item['status'] == 'ok':
                    ledger.add(observation(f"photos.image.{item['number']:03d}",
                                           {'sha256': item['sha256'], 'width': item['width'], 'height': item['height']},
                                           item['source_url'], item['captured_at'], 'source_capture', 'photo',
                                           'Image retrieved; contents still require individual human inspection.'))
            return {'status': 'partial' if any(item['status'] != 'ok' for item in items) else 'complete',
                    'images': len(items), 'thumbnails': sum(item.get('thumbnail_only', False) for item in items),
                    'failed': [item['number'] for item in items if item['status'] != 'ok']}
        # Every downloaded image is an output: a missing/corrupt image invalidates resume.
        existing_images = []
        if (photos_path / 'download-manifest.json').is_file():
            existing_images = [photos_path / item['file'] for item in json.loads((photos_path / 'download-manifest.json').read_text())['images'] if item.get('status') == 'ok']
        result = step('photos', [config / 'photos.json'], [photos_path / 'download-manifest.json', photos_path / 'review.html', *existing_images], get_photos,
                      reason='Missing reviewed photo manifest; run discovery and verify gallery candidates first' if not (config / 'photos.json').is_file() else None, network=True)
        if result['status'] == 'complete':
            items = json.loads((photos_path / 'download-manifest.json').read_text())['images']
            for item in items:
                if item.get('status') == 'ok':
                    result['output_hashes'][str((photos_path / item['file']).relative_to(work))] = digest(photos_path / item['file'])
            for sheet in photos_path.glob('contact-*.jpg'):
                result['output_hashes'][str(sheet.relative_to(work))] = digest(sheet)
            write_json(manifest_path, manifest)
    if 'map' in selected:
        def make_map():
            data = json.loads(bundle_path.read_text())
            metrics = parcel_map.render(data, json.loads((config / 'map.json').read_text()), work / 'parcel-study.png')
            write_json(work / 'parcel-study.png.metrics.json', metrics)
            return {'status': 'partial' if data.get('errors') else 'complete', 'warning': metrics['warning']}
        reason = 'Missing GIS bundle or map config' if not bundle_path.is_file() or not (config / 'map.json').is_file() else None
        if 'gis' in current and current['gis']['status'] in ('failed', 'blocked'):
            reason = 'Current GIS acquisition failed/blocked; refusing to silently map an older bundle'
        step('map', [bundle_path, config / 'map.json'], [work / 'parcel-study.png', work / 'parcel-study.png.metrics.json'], make_map, reason)
    if 'routes' in selected:
        private_profile = Path(profile_path).resolve() if profile_path else root / 'private/buyer_profile.json'
        def get_routes():
            profile = routing.load_json(private_profile)
            rows = routing.evaluate(record['address'], profile, provider, work / 'location-cache.json', departure, refresh)
            write_json(work / 'routes.json', {'slug': slug, 'routes': rows})
            for row in rows:
                ledger.add(observation('routes.' + row['destination'], {k: v for k, v in row.items() if k != 'observed_at'},
                                       'https://routes.googleapis.com/directions/v2:computeRoutes' if provider == 'google' else 'https://router.project-osrm.org',
                                       row['observed_at'], 'inference', 'route', 'Provider routing estimate, not measured driving.'))
            return {'provider': provider, 'destinations': len(rows)}
        step('routes', [root / 'data/properties' / (slug + '.json'), private_profile], [work / 'routes.json'], get_routes,
             reason='Private routing profile missing; supply --profile or use private/buyer_profile.json' if not private_profile.is_file() else None, network=True)
    if 'blind' in selected:
        def blind_check():
            from .blind_valuation import check_record
            errors = check_record(root, record)
            meta = record.get('blind_valuation', {})
            if not isinstance(meta, dict):
                meta = {}
            state = meta.get('status', 'pending')
            detail = {'status': 'complete' if state == 'valued' and not errors else 'partial',
                      'blind_status': state, 'errors': errors,
                      'next': 'Follow docs/blind-valuation.md. The coordinator must prepare a reviewed packet, spawn a fresh no-history subagent, lock/compare/publish its result. This Python runner cannot spawn Work agents.'}
            write_json(work / 'blind-check.json', detail)
            return detail
        step('blind', [root / 'data/properties' / (slug + '.json')], [work / 'blind-check.json'], blind_check)
    if 'checks' in selected:
        def checks():
            report = ledger.report()
            result = validate_repo(root, slug, work / 'evidence.json')[0]
            write_json(work / 'evidence-report.json', report)
            write_json(work / 'validation.json', result)
            return {'status': 'partial' if result['errors'] else 'complete', 'errors': result['errors'], 'warnings': result['warnings']}
        step('checks', [root / 'data/properties' / (slug + '.json'), root / 'evaluations' / (slug + '.md'),
                        root / 'buyer_profile.json', work / 'evidence.json'],
             [work / 'evidence-report.json', work / 'validation.json'], checks)
    manifest['completed_at'] = now()
    manifest['selected_steps'] = selected
    manifest['status'] = 'partial' if any(result['status'] != 'complete' for result in current.values()) else 'captured_review_required'
    write_json(manifest_path, manifest)
    lines = [f'# Research checklist — {record["address"]}', '', 'Research capture only. Production records and Sheet are unchanged.', '']
    lines += [f'- {name}: {result["status"]}' + (f" — {result['reason']}" if result.get('reason') else '') for name, result in current.items()]
    lines += ['', '## Human review still required', ''] + [f'- [ ] {item}' for item in MANUAL_CHECKS]
    if 'checks' in current:
        lines += ['', '## Validation errors', ''] + ['- ' + item for item in current['checks'].get('detail', {}).get('errors', [])]
        lines += ['', '## Validation warnings', ''] + ['- ' + item for item in current['checks'].get('detail', {}).get('warnings', [])]
    (work / 'checklist.md').write_text('\n'.join(lines) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='Exact existing slug/address/parcel ID/listing URL')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--steps', help='Comma-separated subset: gis,photos,map,routes,blind,checks')
    parser.add_argument('--refresh', action='store_true', help='Refetch selected network steps; overwrite working captures, not production records')
    parser.add_argument('--offline', action='store_true', help='Reuse matching completed captures only; make no network requests')
    parser.add_argument('--provider', choices=['osrm', 'google'], default='osrm')
    parser.add_argument('--departure')
    parser.add_argument('--profile', help='Private routing profile, never committed')
    args = parser.parse_args()
    if args.offline and args.refresh:
        parser.error('--offline and --refresh cannot be combined')
    result = run(args.root, args.target, args.steps.split(',') if args.steps else None,
                 args.refresh, args.offline, args.provider, args.departure, args.profile)
    print(f"Report: {args.root / 'private/research' / result['slug'] / 'checklist.md'}")
    if result['status'] == 'partial':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
