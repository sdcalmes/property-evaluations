"""Check reviewed records without modifying facts, ratings or offer judgments."""
import argparse
import hashlib
import html
import json
import math
import re
from pathlib import Path
from .build_site import ROOT, SLUG, PRIVATE_STREET_SHA256, private_markers
from .scoring import score


def private_content(text, profile):
    from urllib.parse import unquote
    text = unquote(html.unescape(text)).casefold()
    if any(marker in text for marker in private_markers(profile)):
        return True
    # Include URL-encoded addresses and JSON escapes, not just generated HTML.
    words = re.findall(r'[a-z0-9]+', re.sub(r'<[^>]+>', ' ', unquote(text)))
    return any(hashlib.sha256(' '.join(words[i:i + size]).encode()).hexdigest() in PRIVATE_STREET_SHA256
               for size in (3, 4) for i in range(len(words) - size + 1))


def check(record, profile, narrative='', evidence=None):
    errors, warnings = [], []
    stage = record.get('research_status', 'reviewed')
    if stage not in ('draft', 'reviewed'):
        errors.append('research_status must be draft or reviewed')
    if stage == 'draft':
        warnings.append('Draft research record: excluded from dashboard; do not sync as a completed Sheet evaluation')
    elif record.get('research_status') == 'reviewed':
        if not record.get('evaluation_date') or 'Research pending' in narrative or '{{ADDRESS}}' in narrative:
            errors.append('Reviewed record is still a placeholder or lacks evaluation_date')
    ratings = record.get('ratings', {})
    if not isinstance(ratings, dict):
        return {'slug': record.get('slug'), 'errors': ['ratings must be an object'], 'warnings': []}
    if not isinstance(record.get('commutes', []), list) or any(not isinstance(t, dict) for t in record.get('commutes', [])):
        return {'slug': record.get('slug'), 'errors': ['commutes must be a list of objects'], 'warnings': []}
    if not isinstance(record.get('storage_fit', {}), dict):
        return {'slug': record.get('slug'), 'errors': ['storage_fit must be an object'], 'warnings': []}
    for key, value in ratings.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or not 0 <= value <= 10):
            errors.append(f'ratings.{key}: expected finite number 0–10 or null')
    if not errors:
        result = score(record, profile)
        for field, actual in [('buyer_fit_score', result['fit_score_0_to_10']),
                              ('score_weight_coverage_percent', result['weight_coverage_percent'])]:
            saved = record.get(field)
            if saved is not None and actual is not None:
                if isinstance(saved, bool) or not isinstance(saved, (int, float)) or not math.isfinite(saved) or abs(saved - actual) > .011:
                    errors.append(f'{field}: saved {saved} differs from helper {actual}')
    for low, high in [('estimated_value_low', 'estimated_value_high'), ('caution_price', 'walk_away_price')]:
        a, b = record.get(low), record.get(high)
        for field, value in [(low, a), (high, b)]:
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                errors.append(f'{field}: expected nonnegative finite number')
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (a, b)) and a > b:
            errors.append(f'{low} exceeds {high}')
    for field in ('opening_offer', 'reasonable_range'):
        value = record.get(field)
        # Validate an explicit dollar interval, without interpreting narrative qualifiers.
        match = re.search(r'\$([\d,]+)\s*[–—-]\s*\$?([\d,]+)', value or '') if isinstance(value, str) else None
        if match and int(match[1].replace(',', '')) > int(match[2].replace(',', '')):
            errors.append(f'{field}: reversed dollar range')
    for name in ('lot_acres', 'gis_lot_acres', 'listing_lot_acres'):
        value = record.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            errors.append(f'{name}: expected nonnegative finite number')
    acres, mapped = record.get('lot_acres'), record.get('gis_lot_acres')
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (acres, mapped)):
        if abs(acres - mapped) > max(.02, acres * .02):
            warnings.append('Exclusive and GIS acreage differ materially; explain the source conflict')
    storage = record.get('storage_fit', {})
    if storage.get('subdivision') is True and storage.get('large_workshop_required') is True:
        errors.append('Subdivision record treats a large workshop as required; conflicts with buyer profile')
    if re.search(r'(?:must have|requires?|deal.?breaker)[^.\n]{0,65}(?:30\s*[x×]\s*40\s*(?:workshop|shop))', narrative, re.I):
        warnings.append('Review narrative workshop requirement against the current garage-first preference')
    for trip in record.get('commutes', []):
        if any(key in trip for key in ('address', 'routing_address', 'user_entered_address')):
            errors.append('Commute contains a private address field; publish labels/results only')
        if trip.get('traffic_aware') and trip.get('comparison_basis') != 'static_to_static':
            warnings.append(f"{trip.get('destination', 'Route')}: traffic time may be compared to a no-traffic baseline; retain a matched comparison")
    if private_content(json.dumps(record) + '\n' + narrative, profile):
        errors.append('Private destination address detected in public record/narrative')
    if evidence is None:
        warnings.append('No evidence ledger attached; source freshness and conflicts are not automatically checked')
    else:
        errors.extend('Evidence: ' + row['error'] for row in evidence['invalid'])
        warnings.extend(f"Stale evidence: {row['fact']} ({row['age_days']} days)" for row in evidence['stale'])
        warnings.extend('Unresolved evidence difference: ' + row['fact'] for row in evidence['conflicts'])
        warnings.extend('Unknown evidence: ' + fact for fact in evidence['unknown_facts'])
        warnings.extend('Evidence not yet logged: ' + fact for fact in evidence.get('missing_facts', []))
    return {'slug': record.get('slug'), 'errors': errors, 'warnings': warnings,
            'limitations': 'Numeric/structured checks and targeted wording flags; not a semantic review of all prose or a value opinion.'}


def validate_repo(root=ROOT, slug=None, ledger_path=None, as_of=None):
    from .evidence import Ledger
    root = Path(root)
    if slug and not SLUG.fullmatch(slug):
        raise ValueError('Invalid property slug')
    profile = json.loads((root / 'buyer_profile.json').read_text())
    paths = sorted((root / 'data/properties').glob('*.json'))
    results, identities = [], {}
    for path in paths:
        record = json.loads(path.read_text())
        identities.setdefault(record.get('parcel_id') or record.get('address', '').casefold().strip(), []).append(path.stem)
        if slug and path.stem != slug:
            continue
        name = record.get('evaluation_markdown')
        errors = []
        if record.get('slug') != path.stem or not SLUG.fullmatch(path.stem) or name != path.stem + '.md':
            errors.append('Record/filename/narrative identity mismatch')
            narrative = ''
        elif not (root / 'evaluations' / name).is_file():
            errors.append('Missing narrative')
            narrative = ''
        else:
            narrative = (root / 'evaluations' / name).read_text()
        public_path = root / 'data/evidence' / (path.stem + '.json')
        evidence = None
        if public_path.is_file():
            from .evidence_public import validate_summary
            try:
                public = validate_summary(public_path, path.stem, profile, as_of)
                if not ledger_path:
                    evidence = public.report(as_of)
            except (ValueError, KeyError, TypeError) as exc:
                errors.append('Public evidence: ' + str(exc))
        if ledger_path:
            evidence = Ledger(ledger_path, path.stem).report(as_of)
        result = check(record, profile, narrative, evidence)
        from .blind_valuation import check_record
        result['errors'] = errors + result['errors'] + check_record(root, record)
        results.append(result)
    if slug and not results:
        raise ValueError('Property record not found')
    for names in identities.values():
        if len(names) > 1:
            for result in results:
                if result['slug'] in names:
                    result['errors'].append('Duplicate property identity: ' + ', '.join(names))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--slug')
    parser.add_argument('--ledger')
    parser.add_argument('--as-of')
    parser.add_argument('--public-sources', action='store_true', help='Scan Git-tracked and nonignored text sources for known private addresses')
    args = parser.parse_args()
    if args.ledger and not args.slug:
        parser.error('--ledger requires --slug')
    results = validate_repo(args.root, args.slug, args.ledger, args.as_of)
    if args.public_sources:
        import subprocess
        profile = json.loads((args.root / 'buyer_profile.json').read_text())
        names = subprocess.check_output(['git', '-C', str(args.root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z']).decode().split('\0')
        leaks = []
        for name in names:
            if not name:
                continue
            path = args.root / name
            if not path.is_file():
                continue
            try:
                if private_content(path.read_text(encoding='utf-8'), profile):
                    leaks.append(name)
            except UnicodeDecodeError:
                pass
        if leaks:
            results.append({'slug': 'public-source-privacy', 'errors': ['Private destination detected: ' + name for name in leaks], 'warnings': []})
    print(json.dumps(results, indent=2))
    if any(item['errors'] for item in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
