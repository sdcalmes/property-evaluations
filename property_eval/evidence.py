"""Append-only research observations. Captures are evidence, not conclusions."""
import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from .research_io import now, write_json

BASES = {'official_record', 'listing_claim', 'visual_observation', 'inference', 'unknown', 'source_capture'}
REVIEW_FACTS = ('listing.status', 'listing.current_list_price', 'tax.annual_bill',
                'systems.improvements', 'restrictions.small_shed', 'garden.usability')

MAX_AGE_DAYS = {'listing': 1, 'route': 7, 'photo': 30, 'gis': 365,
                'tax': 400, 'permit': 365, 'document': 365, 'analysis': 30}


def timestamp(value):
    if len(value) == 10:
        return datetime.combine(date.fromisoformat(value), datetime.min.time(), timezone.utc)
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Evidence timestamp must include a timezone, or be a date-only source date')
    return result.astimezone(timezone.utc)


def observation(fact, value, source_url, observed_at, basis, kind, note='', event_date=None):
    if not fact or basis not in BASES or kind not in MAX_AGE_DAYS:
        raise ValueError('Invalid fact, basis or source kind')
    timestamp(observed_at)
    if basis != 'unknown' and not source_url:
        raise ValueError('Known observations need a source URL')
    if source_url and urlsplit(source_url).scheme not in ('https', 'http'):
        raise ValueError('Evidence sources must use HTTP(S)')
    if basis == 'unknown' and value is not None:
        raise ValueError('Unknown evidence must have a null value')
    if event_date:
        date.fromisoformat(event_date)
    item = {'fact': fact, 'value': value, 'source_url': source_url, 'observed_at': observed_at,
            'basis': basis, 'kind': kind, 'note': note, 'event_date': event_date}
    item['id'] = hashlib.sha256(json.dumps(item, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return item


class Ledger:
    def __init__(self, path, slug):
        self.path, self.slug = Path(path), slug
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {
            'schema_version': 1, 'slug': slug, 'observations': []}
        if self.data.get('slug') != slug or self.data.get('schema_version') != 1:
            raise ValueError('Evidence ledger identity/schema mismatch')

    def add(self, item):
        # Validate even imported observations; preserve the original observation date.
        clean = observation(**{k: item[k] for k in ('fact', 'value', 'source_url', 'observed_at', 'basis', 'kind')},
                            note=item.get('note', ''), event_date=item.get('event_date'))
        if clean['id'] not in {row['id'] for row in self.data['observations']}:
            self.data['observations'].append(clean)
            write_json(self.path, self.data)
        return clean['id']

    def report(self, as_of=None):
        current = timestamp(as_of) if as_of else datetime.now(timezone.utc)
        stale, invalid, groups, unknown = [], [], {}, []
        for index, item in enumerate(self.data['observations']):
            try:
                clean = observation(**{k: item[k] for k in ('fact', 'value', 'source_url', 'observed_at', 'basis', 'kind')},
                                    note=item.get('note', ''), event_date=item.get('event_date'))
                if clean['id'] != item.get('id'):
                    raise ValueError('Observation hash mismatch')
                age = (current - timestamp(item['observed_at'])).total_seconds() / 86400
                if age < -1/1440:
                    raise ValueError('Observation date is in the future')
                if age > MAX_AGE_DAYS[item['kind']]:
                    stale.append({'id': item['id'], 'fact': item['fact'], 'age_days': round(age, 1)})
                if item['basis'] == 'unknown':
                    unknown.append(item['fact'])
                else:
                    groups.setdefault(item['fact'], []).append(item)
            except (KeyError, TypeError, ValueError) as exc:
                invalid.append({'index': index, 'error': str(exc)})
        conflicts = []
        for fact, items in groups.items():
            values = {json.dumps(item['value'], sort_keys=True) for item in items}
            if len(values) > 1:
                conflicts.append({'fact': fact, 'observation_ids': [item['id'] for item in items],
                                  'note': 'Different observations; may reflect a real change over time. Resolve in the narrative; never silently overwrite.'})
        return {'slug': self.slug, 'as_of': current.isoformat(), 'observation_count': len(self.data['observations']),
                'stale': stale, 'conflicts': conflicts, 'invalid': invalid, 'unknown_facts': sorted(set(unknown)),
                'missing_facts': [fact for fact in REVIEW_FACTS if fact not in {row.get('fact') for row in self.data['observations']}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--slug', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add')
    add.add_argument('--fact', required=True)
    add.add_argument('--value', required=True, help='JSON: number, quoted string, object, boolean or null')
    add.add_argument('--source-url')
    add.add_argument('--observed-at', required=True)
    add.add_argument('--basis', choices=sorted(BASES), required=True)
    add.add_argument('--kind', choices=sorted(MAX_AGE_DAYS), required=True)
    add.add_argument('--note', default='')
    add.add_argument('--event-date')
    check = sub.add_parser('report')
    check.add_argument('--as-of')
    args = parser.parse_args()
    ledger = Ledger(args.ledger, args.slug)
    if args.command == 'add':
        print(ledger.add(observation(args.fact, json.loads(args.value), args.source_url,
                                    args.observed_at, args.basis, args.kind, args.note, args.event_date)))
    else:
        result = ledger.report(args.as_of)
        print(json.dumps(result, indent=2))
        if result['invalid']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
