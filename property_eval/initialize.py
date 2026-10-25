"""Create an unknown-filled draft for a new property; refuse duplicate identities."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .build_site import ROOT, SLUG
from .research_io import now, write_json
from .validate import private_content


def address_key(value):
    # Primary address match is conservative across postal/municipal naming differences.
    text = re.sub(r'[^a-z0-9 ]', ' ', value.split(',')[0].casefold())
    aliases = {'street':'st', 'drive':'dr', 'lane':'ln', 'court':'ct', 'avenue':'ave', 'road':'rd', 'circle':'cir'}
    return ' '.join(aliases.get(word, word) for word in text.split())


def url_key(value):
    url = urlsplit(value or '')
    return (url.netloc.casefold() + url.path.rstrip('/')).casefold()


def initialize(root, address, listing_url=None, parcel_id=None, slug=None, master_database_id=None):
    root = Path(root)
    if not address.strip():
        raise ValueError('A nonempty property address is required')
    if listing_url and (urlsplit(listing_url).scheme not in ('http', 'https') or not urlsplit(listing_url).netloc):
        raise ValueError('Listing URL must be HTTP(S)')
    profile = json.loads((root / 'buyer_profile.json').read_text())
    if private_content(' '.join(str(value or '') for value in (address, listing_url, parcel_id, master_database_id)), profile):
        raise ValueError('Private destination detected; do not create a public property record')
    slug = slug or re.sub(r'[^a-z0-9]+', '-', address.split(',')[0].casefold()).strip('-')
    if not SLUG.fullmatch(slug):
        raise ValueError('Invalid slug')
    for path in (root / 'data/properties').glob('*.json'):
        existing = json.loads(path.read_text())
        reasons = []
        if existing['slug'] == slug:
            reasons.append('slug')
        if address_key(existing.get('address', '')) == address_key(address):
            reasons.append('address')
        if parcel_id and re.sub(r'\W', '', str(existing.get('parcel_id') or '')).upper() == re.sub(r'\W', '', parcel_id).upper():
            reasons.append('parcel')
        if listing_url and existing.get('listing_url') and url_key(existing['listing_url']) == url_key(listing_url):
            reasons.append('listing URL')
        if master_database_id and existing.get('master_database_id', '').casefold() == master_database_id.casefold():
            reasons.append('Master Database ID')
        if reasons:
            raise ValueError(f"Possible existing property {existing['slug']} matched {', '.join(reasons)}; review/reuse it. Nothing was written.")
    record_path = root / 'data/properties' / (slug + '.json')
    narrative_path = root / 'evaluations' / (slug + '.md')
    config = root / 'research' / slug
    evidence_path = root / 'data/evidence' / (slug + '.json')
    if record_path.exists() or narrative_path.exists() or config.exists() or evidence_path.exists():
        raise ValueError('An output already exists; refusing to overwrite research')
    fields = ('status current_list_price original_list_price list_date beds baths full_baths half_baths year_built '
              'above_grade_sqft below_grade_finished_sqft garage lot_acres municipality schools utilities hoa annual_taxes '
              'tax_year buyer_fit_score score_weight_coverage_percent estimated_value_low estimated_value_high pricing_conclusion '
              'opening_offer reasonable_range caution_price walk_away_price evaluation_date').split()
    record = {key: None for key in fields}
    record.update(slug=slug, address=address.strip(), listing_url=listing_url, parcel_id=parcel_id,
                  master_database_id=master_database_id, research_status='draft', created_at=now(),
                  blind_valuation={'method':'work_subagent_packet_only','status':'pending'},
                  ratings={key: None for key in profile['scoring']['weights']}, commutes=[],
                  major_positives=[], major_concerns=[], uncertainties=['Research pending; draft is not an evaluation.'],
                  evaluation_markdown=slug + '.md')
    template = (root / 'evaluations/TEMPLATE.md').read_text().replace('{{ADDRESS}}', address.strip())
    skeletons = {
        'blind-input.draft.json': {'as_of':None,'subject':{'market_area':None},'comps':[],'images':[]},
        'gis.draft.json': {'parcel_id': parcel_id, 'parcel_id_field': None, 'parcel_layer': None,
                           'spatial_reference': None, 'units': None, 'layers': {}},
        'photos.draft.json': {'listing_url': listing_url, 'discovered_at': None, 'images': [],
                             'review_required': 'Discover actual gallery URLs, inspect candidates/count/order; do not guess URLs.'},
        'map.draft.json': {'title': address.strip(), 'spatial_reference': None, 'street_guides': [],
                           'study_areas': [], 'contour_layers': {}, 'source_note': 'Not configured. Verify geometry/units and legal limitations.'}}
    # Preflight above is read-only. Create only new outputs after identity checks pass.
    write_json(record_path, record)
    narrative_path.parent.mkdir(parents=True, exist_ok=True)
    narrative_path.write_text('<!-- Research pending: draft excluded from dashboard. -->\n\n' + template)
    for name, data in skeletons.items():
        write_json(config / name, data)
    (config / 'README.md').write_text(f'''# Research setup — {address.strip()}

This is a new draft, not researched facts. Check connected Master Database history
before treating it as new; set the verified `master_database_id` when matched/created.
Fill verified values and rename *.draft.json to gis.json/photos.json/map.json as each
becomes usable. Draft names deliberately prevent the runner from querying null inputs.
Discover county services/fields/units and parcel identity. Configure geometry, garden
and optional small-shed study coordinates individually. Do not copy another lot's
setbacks, zoning, workshop expectations or coordinates. See ../../docs/research.md.

Run `python -m property_eval.research {slug}` after setup. Complete the evaluation
and reviewed public evidence summary, then set research_status=reviewed and the actual
evaluation_date. Drafts are excluded from the dashboard and must not be written as
completed evaluations to the Sheet. Unknown facts stay null.
''')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--address', required=True)
    parser.add_argument('--listing-url')
    parser.add_argument('--parcel-id')
    parser.add_argument('--slug')
    parser.add_argument('--master-database-id')
    args = parser.parse_args()
    record = initialize(args.root, args.address, args.listing_url, args.parcel_id, args.slug, args.master_database_id)
    print(json.dumps({'slug': record['slug'], 'research_status': 'draft', 'dashboard_visible': False,
                      'next': 'Check Sheet identity, configure research, complete review before publishing.'}, indent=2))


if __name__ == '__main__':
    main()
