"""Export explicitly selected, reviewed observations for safe cross-session reuse."""
import argparse
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from .build_site import ROOT, SLUG
from .evidence import Ledger, observation
from .research_io import now, write_json
from .validate import private_content

PUBLIC_FACTS = {'listing.status', 'listing.current_list_price', 'tax.annual_bill',
                'systems.improvements', 'restrictions.small_shed', 'garden.usability',
                'parcel.id', 'parcel.exclusive_acres', 'parcel.zoning',
                'risks.development', 'photos.review', 'comps.condition'}
SECRET_KEYS = {'key', 'api_key', 'apikey', 'token', 'access_token', 'authorization',
               'signature', 'sig', 'destination', 'destinations', 'waypoints'}
PRIVATE_FIELDS = {'routing_address', 'user_entered_address', 'destination_address',
                  'password', 'api_key', 'token', 'latitude', 'longitude'}


def inspect_item(item, profile):
    if item.get('fact') not in PUBLIC_FACTS:
        raise ValueError('Fact is not in the reviewed public-summary allowlist')
    if item.get('basis') == 'source_capture':
        raise ValueError('Raw captures are not reviewed findings; log a reviewed observation first')
    if private_content(json.dumps(item), profile):
        raise ValueError('Private destination detected in evidence')
    url = urlsplit(item.get('source_url') or '')
    if url.username or url.password or any(key.casefold() in SECRET_KEYS or key.casefold().startswith(('x-amz-', 'x-goog-'))
                                         for key, _ in parse_qsl(url.query)):
        raise ValueError('Credential-bearing or private route URL cannot be public evidence')
    if '/maps/dir' in url.path.casefold():
        raise ValueError('Publish a provider homepage, not an address-bearing route URL')
    def walk(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if key.casefold() in PRIVATE_FIELDS:
                    raise ValueError('Private input/cache field cannot be public evidence')
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
    walk(item)
    clean = observation(**{k: item[k] for k in ('fact','value','source_url','observed_at','basis','kind')},
                        note=item.get('note',''), event_date=item.get('event_date'))
    if clean['id'] != item.get('id'):
        raise ValueError('Evidence observation hash mismatch')


def validate_summary(path, slug, profile, as_of=None):
    ledger = Ledger(path, slug)
    review = ledger.data.get('public_review', {})
    if review.get('reviewed') is not True or not review.get('reviewed_at'):
        raise ValueError('Public evidence summary lacks explicit review metadata')
    from .evidence import timestamp
    timestamp(review['reviewed_at'])
    if not ledger.data['observations']:
        raise ValueError('Public evidence summary is empty')
    for item in ledger.data['observations']:
        inspect_item(item, profile)
    report = ledger.report(as_of)
    if report['invalid']:
        raise ValueError('Invalid public evidence: ' + json.dumps(report['invalid']))
    return ledger


def export(root, slug, ledger_path, selected_ids, reviewed=False, profile_path=None):
    root = Path(root)
    if not SLUG.fullmatch(slug) or not (root/'data/properties'/f'{slug}.json').is_file():
        raise ValueError('Export requires an existing property slug')
    if not reviewed or not selected_ids:
        raise ValueError('Select observation IDs and explicitly attest --reviewed after inspection')
    profile = json.loads(Path(profile_path).read_text()) if profile_path else json.loads((root/'buyer_profile.json').read_text())
    ledger = Ledger(ledger_path, slug)
    by_id = {row['id']: row for row in ledger.data['observations']}
    if any(key not in by_id for key in selected_ids):
        raise ValueError('Selected observation ID not found; nothing exported')
    target = root/'data/evidence'/f'{slug}.json'
    # Retain previously reviewed evidence (including conflicts/history) rather than replacing it.
    output = validate_summary(target, slug, profile) if target.exists() else Ledger(target, slug)
    merged = {row['id']: row for row in output.data['observations']}
    for key in selected_ids:
        inspect_item(by_id[key], profile)
        merged[key] = by_id[key]
    draft = {'schema_version':1, 'slug':slug, 'observations':list(merged.values()),
             'public_review':{'reviewed':True,'reviewed_at':now(),
                              'scope':'Selected public findings only; original observation dates retained. No raw captures or private routing inputs.'}}
    # Validate in memory before one atomic write. No unreviewed/invalid partial export.
    original = output.data
    output.data = draft
    report = output.report()
    if report['invalid']:
        output.data = original
        raise ValueError('Invalid/future evidence; nothing exported')
    write_json(target, draft)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--slug',required=True)
    parser.add_argument('--ledger',required=True)
    parser.add_argument('--ids',required=True,help='Comma-separated explicitly reviewed observation IDs; no export-all mode')
    parser.add_argument('--reviewed',action='store_true',help='Attest that each selected finding/source is suitable for public sharing')
    parser.add_argument('--profile',help='Optional private profile for additional address checks; never exported')
    args=parser.parse_args()
    print(export(args.root,args.slug,args.ledger,args.ids.split(','),args.reviewed,args.profile))


if __name__=='__main__':
    main()
