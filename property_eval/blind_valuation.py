"""Work subagent packet-only valuation. Procedural separation, not a tool sandbox."""
import argparse
import hashlib
import json
import math
import re
import uuid
from datetime import date
from pathlib import Path
from .build_site import ROOT, SLUG
from .research_io import now, write_json
from .evidence import timestamp
from .validate import private_content

METHOD = 'work_subagent_packet_only'
LIMITATION = 'Fresh-context, packet-only instructions and exposure attestations; shared Work tools/files are not access-isolated. Hashes detect changes, not proof of blindness.'
SUBJECT_FIELDS = {'market_area','property_type','year_built','beds','full_baths','half_baths',
                  'above_grade_sqft','below_grade_finished_sqft','exclusive_lot_acres',
                  'garage_spaces','garage_attached','condition','land','features','limitations','prior_sales'}
COMP_FIELDS = (SUBJECT_FIELDS - {'prior_sales'}) | {'comp_id','sale_price','sale_date','distance_miles','same_subdivision'}
TEXT_FIELDS = {'market_area','property_type','land'}
LIST_FIELDS = {'features','limitations'}
CONDITION_FIELDS = {'kitchen','baths','roof','hvac','windows','siding','basement','overall'}
BOOL_FIELDS = {'garage_attached','same_subdivision'}
NUM_FIELDS = SUBJECT_FIELDS - TEXT_FIELDS - LIST_FIELDS - BOOL_FIELDS - {'condition','prior_sales'}
IDENTITY_FIELDS = ('slug','address','parcel_id','beds','full_baths','half_baths','year_built',
                   'above_grade_sqft','below_grade_finished_sqft','garage','lot_acres','utilities','zoning')
RESULT_FIELDS = {'run_id','packet_sha256','status','subject_asking_price_exposed','other_exposure',
                 'tools_used','value_low','value_mid','value_high','confidence','comp_analysis',
                 'rationale','assumptions','missing_evidence'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_sha(record):
    return sha({field:record.get(field) for field in IDENTITY_FIELDS})


def keys(value, allowed, label):
    if not isinstance(value,dict) or set(value)-allowed:
        raise ValueError(f'{label}: expected object with allowlisted fields only')


def number(value, label, positive=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f'{label}: expected finite {"positive" if positive else "nonnegative"} number')


def excluded_amounts(record):
    values=[record.get(key) for key in ('current_list_price','original_list_price','estimated_value_low',
                                       'estimated_value_high','caution_price','walk_away_price')]
    for key in ('opening_offer','reasonable_range'):
        values += [float(v.replace(',','')) for v in re.findall(r'\$([\d,]+)',str(record.get(key) or ''))]
    return {float(v) for v in values if isinstance(v,(int,float)) and not isinstance(v,bool) and v>0}


def neutral_text(text, label, profile=None, forbidden=()):
    if not isinstance(text,str) or len(text)>2000:
        raise ValueError(f'{label}: expected short neutral text')
    if re.search(r'https?://|www\.|[$€£]|\b(?:asking|list[ -]?price|price[ -]?(?:cut|reduction)|priced|overpriced|underpriced|bargain|zestimate|avm|offer|previous valuation|below market)\b',text,re.I):
        raise ValueError(f'{label}: price/value cue or URL; rewrite as sourced neutral facts')
    if re.search(r'\b\d+(?:\.\d+)?\s*(?:k|million|thousand)\b',text,re.I):
        raise ValueError(f'{label}: monetary-looking shorthand; use typed fields')
    for value in forbidden:
        if re.search(r'(?<!\d)'+re.escape(str(int(value)))+r'(?!\d)',text.replace(',','')):
            raise ValueError(f'{label}: excluded subject amount appears in text')
    if profile and private_content(text,profile):
        raise ValueError(f'{label}: private destination detected')
    return text


def clean_property(value, as_of, profile=None, forbidden=(), comp=False):
    allowed=COMP_FIELDS if comp else SUBJECT_FIELDS
    keys(value,allowed,'comp' if comp else 'subject')
    out={}
    for key,item in value.items():
        if item is None:
            out[key]=None
        elif key in TEXT_FIELDS:
            out[key]=neutral_text(item,key,profile,forbidden)
        elif key in LIST_FIELDS:
            if not isinstance(item,list) or len(item)>30:
                raise ValueError(f'{key}: expected bounded text list')
            out[key]=[neutral_text(v,key,profile,forbidden) for v in item]
        elif key=='condition':
            keys(item,CONDITION_FIELDS,'condition')
            out[key]={k:neutral_text(v,'condition.'+k,profile,forbidden) for k,v in item.items()}
        elif key in BOOL_FIELDS:
            if not isinstance(item,bool):raise ValueError(f'{key}: expected boolean or null')
            out[key]=item
        elif key=='prior_sales':
            if not isinstance(item,list) or len(item)>10:raise ValueError('prior_sales must be a bounded list')
            out[key]=[]
            for sale in item:
                keys(sale,{'sale_date','sale_price'},'prior sale')
                if set(sale)!={'sale_date','sale_price'}:raise ValueError('Prior sale needs date and completed sale price')
                number(sale['sale_price'],'prior sale price',True)
                if date.fromisoformat(sale['sale_date'])>as_of:raise ValueError('Future subject sale')
                out[key].append(dict(sale))
        elif key=='comp_id':
            if not isinstance(item,str) or not re.fullmatch(r'C[0-9]{1,3}',item):raise ValueError('Use anonymous comp IDs C1, C2, ...')
            out[key]=item
        elif key=='sale_date':
            if date.fromisoformat(item)>as_of:raise ValueError('Comparable sale is after valuation date')
            out[key]=item
        else:
            number(item,key,positive=key=='sale_price')
            out[key]=item
    if not out.get('market_area'):
        raise ValueError('Market area is required; do not anonymize away relevant location context')
    if comp and any(out.get(key) is None for key in ('comp_id','sale_date','sale_price')):
        raise ValueError('Only verified completed sales with ID/date/price belong in comps')
    return out


def validate_packet(packet, profile=None, forbidden=()):
    keys(packet,{'schema_version','run_id','method','as_of','subject','comps','images'},'packet')
    if packet.get('schema_version')!=1 or packet.get('method')!=METHOD or not re.fullmatch(r'[a-f0-9]{32}',packet.get('run_id','')):
        raise ValueError('Packet identity/schema mismatch')
    as_of=date.fromisoformat(packet['as_of'])
    clean_property(packet['subject'],as_of,profile,forbidden)
    if not isinstance(packet['comps'],list) or len(packet['comps'])>20:raise ValueError('Use at most 20 sold comps')
    for comp in packet['comps']:clean_property(comp,as_of,profile,forbidden,True)
    ids=[comp['comp_id'] for comp in packet['comps']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate comp IDs')
    if not isinstance(packet['images'],list) or len(packet['images'])>60:raise ValueError('Use at most 60 reviewed images')
    for index,item in enumerate(packet['images'],1):
        if set(item)!={'image_id','property_id','file','sha256','width','height'} or item['image_id']!=f'I{index:02d}' or item['file']!=f'I{index:02d}.jpg' or not re.fullmatch(r'[a-f0-9]{64}',item['sha256']):
            raise ValueError('Invalid anonymous image manifest')
        if item['property_id'] not in {'Subject',*ids}:raise ValueError('Image must identify Subject or an included comp')


def once(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as handle:
        handle.write(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def prepare(root, slug, intake, reviewed=False, profile_path=None):
    from PIL import Image,ImageOps
    root=Path(root).resolve()
    if not SLUG.fullmatch(slug):raise ValueError('Invalid property slug')
    record=json.loads((root/'data/properties'/f'{slug}.json').read_text())
    if not reviewed:raise ValueError('Review all facts, prose and image overlays before --reviewed')
    keys(intake,{'as_of','subject','comps','images'},'reviewed intake')
    profile=json.loads(Path(profile_path).read_text()) if profile_path else json.loads((root/'buyer_profile.json').read_text())
    forbidden=excluded_amounts(record)
    run_id=uuid.uuid4().hex
    packet={'schema_version':1,'run_id':run_id,'method':METHOD,'as_of':intake['as_of'],
            'subject':intake['subject'],'comps':intake.get('comps',[]),'images':[]}
    validate_packet(packet,profile,forbidden)
    if not isinstance(intake.get('images',[]),list) or len(intake.get('images',[]))>60:raise ValueError('Too many images')
    assets=[]
    for index,item in enumerate(intake.get('images',[]),1):
        keys(item,{'path','price_overlay_checked','property_id'},'image input')
        if item.get('price_overlay_checked') is not True:raise ValueError('Inspect every image for price overlays and portal UI')
        import io
        with Image.open(item['path']) as source:
            image=ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((2000,2000))
            raw=io.BytesIO();image.save(raw,format='JPEG',quality=92)
            data=raw.getvalue()
            info={'image_id':f'I{index:02d}','property_id':item.get('property_id','Subject'),'file':f'I{index:02d}.jpg',
                  'sha256':hashlib.sha256(data).hexdigest(),'width':image.width,'height':image.height}
        assets.append((info['file'],data));packet['images'].append(info)
    validate_packet(packet,profile,forbidden)
    folder=root/'private/blind-valuations'/run_id
    folder.mkdir(parents=True,exist_ok=False)
    for filename,data in assets:(folder/filename).write_bytes(data)
    once(folder/'packet.json',packet)
    once(folder/'coordinator.private.json',{'slug':slug,'record_subject_sha256':record_sha(record),
         'prepared_at':now(),'packet_sha256':sha(packet),'reviewed':True})
    result_example={'run_id':run_id,'packet_sha256':sha(packet),'status':'insufficient_evidence',
        'subject_asking_price_exposed':False,'other_exposure':[],'tools_used':['provided_packet'],
        'value_low':None,'value_mid':None,'value_high':None,'confidence':'not_applicable','comp_analysis':[],
        'rationale':'Explain evidence sufficiency.','assumptions':[],'missing_evidence':['Explain what is missing.']}
    handoff=f'''You are the independent market valuation subagent. This must be a fresh context with no inherited conversation history.
Use ONLY the packet below and the explicitly listed local images. Do not browse, search, read the repository, inspect other files, or contact other agents. Do not read coordinator.private.json. These are procedural instructions; tools/files remain shared.
Estimate market value from completed sold comps, factual condition and location, not buyer preferences. Relevant prior completed subject sales are permitted. No asking price or prior valuation should be supplied.
If you encounter a subject asking price, previous valuation, outside opinion or prohibited source in ANY context/tool, return status=contaminated with null values and describe the exposure. Do not try to forget it.
Return status=insufficient_evidence with null values when evidence is inadequate; a numerical estimate is not mandatory. Otherwise status=valued requires at least two sold comps, ordered positive low/mid/high values, confidence low/medium/high, and comp_analysis weights summing to 1. Include every supplied comp (zero weight with explanation is allowed).
Each comp_analysis entry: {{"comp_id":"C1","weight":1.0,"adjusted_value":null,"reasoning":"Specific differences and adjustment direction; avoid false precision."}}. Dollar adjustments may be described only when supported. No offers or asking-price comparison.
Return JSON only with exactly the fields in this example (replace content appropriately):
{json.dumps(result_example)}
For tools_used report only provided_packet and, if inspected, provided_images. Return JSON to the coordinator; do not write or lock your own result.
PACKET:
{json.dumps(packet,indent=2)}
ALLOWED IMAGE FILES:
{json.dumps([str(folder/i['file']) for i in packet['images']])}
'''
    (folder/'handoff.txt').write_text(handoff)
    return folder


def verify_run(folder):
    folder=Path(folder)
    packet=json.loads((folder/'packet.json').read_text())
    meta=json.loads((folder/'coordinator.private.json').read_text())
    validate_packet(packet)
    if sha(packet)!=meta['packet_sha256'] or folder.name!=packet['run_id']:
        raise ValueError('Packet was changed after preparation')
    for item in packet['images']:
        if file_sha(folder/item['file'])!=item['sha256']:raise ValueError('Image changed/missing after preparation')
    return packet,meta


def validate_result(result, packet):
    keys(result,RESULT_FIELDS,'result')
    if set(result)!=RESULT_FIELDS:raise ValueError('Missing result fields')
    if result['run_id']!=packet['run_id'] or result['packet_sha256']!=sha(packet):raise ValueError('Result belongs to another packet/run')
    if not isinstance(result['subject_asking_price_exposed'],bool):raise ValueError('Exposure attestation must be boolean')
    for key in ('other_exposure','tools_used','assumptions','missing_evidence'):
        if not isinstance(result[key],list) or len(result[key])>50 or any(not isinstance(v,str) or len(v)>4000 for v in result[key]):
            raise ValueError(f'{key}: expected bounded text list')
    if not isinstance(result['rationale'],str) or not result['rationale'].strip() or len(result['rationale'])>12000:raise ValueError('Result needs a bounded rationale')
    prose = ' '.join([result['rationale'], *result['assumptions'], *result['missing_evidence'],
                      *[str(c.get('reasoning','')) for c in result['comp_analysis'] if isinstance(c,dict)]]) if isinstance(result['comp_analysis'],list) else result['rationale']
    if result['status'] != 'contaminated' and re.search(r'https?://|\b(?:asking|list[ -]?price|zestimate|avm|overpriced|underpriced|offer)\b',prose,re.I):
        raise ValueError('Price/source/offer references in result prose; check contamination and keep the independent rationale packet-only')
    exposed=result['subject_asking_price_exposed'] or bool(result['other_exposure']) or bool(set(result['tools_used'])-{'provided_packet','provided_images'})
    if exposed and result['status']!='contaminated':raise ValueError('Exposed/prohibited-source result must be contaminated, never valued')
    if result['status'] not in ('valued','insufficient_evidence','contaminated'):raise ValueError('Invalid result status')
    values=[result[k] for k in ('value_low','value_mid','value_high')]
    if result['status']!='valued':
        if any(v is not None for v in values):raise ValueError('Non-valued result must have null values')
        if result['confidence']!='not_applicable':raise ValueError('Non-valued confidence must be not_applicable')
        if result['status']=='insufficient_evidence' and not result['missing_evidence']:raise ValueError('State missing evidence')
        if result['status']=='contaminated' and not exposed:raise ValueError('State the actual contamination')
    else:
        for value in values:number(value,'valuation',True)
        if values!=sorted(values):raise ValueError('Valuation must be low <= mid <= high')
        if result['confidence'] not in ('low','medium','high') or len(packet['comps'])<2:raise ValueError('Valued result needs confidence and at least two sold comps')
        if 'provided_packet' not in result['tools_used']:raise ValueError('Attest use of provided packet')
    if not isinstance(result['comp_analysis'],list):raise ValueError('comp_analysis must be a list')
    known={c['comp_id'] for c in packet['comps']};seen=set();weight=0
    for comp in result['comp_analysis']:
        keys(comp,{'comp_id','weight','adjusted_value','reasoning'},'comp analysis')
        if set(comp)!={'comp_id','weight','adjusted_value','reasoning'} or comp['comp_id'] not in known or comp['comp_id'] in seen:raise ValueError('Unknown/duplicate/incomplete comp analysis')
        number(comp['weight'],'comp weight')
        if comp['weight']>1:raise ValueError('Comp weight exceeds 1')
        if comp['adjusted_value'] is not None:number(comp['adjusted_value'],'adjusted value',True)
        if not isinstance(comp['reasoning'],str) or not comp['reasoning'].strip():raise ValueError('Explain comp differences')
        seen.add(comp['comp_id']);weight+=comp['weight']
    if result['status']=='valued' and (seen!=known or abs(weight-1)>1e-6):raise ValueError('Explain all comps; weights must sum to 1')


def lock(folder, result, agent_id, fresh_context=False, packet_only=False):
    packet,meta=verify_run(folder)
    if not agent_id or not fresh_context or not packet_only:raise ValueError('Record actual fresh subagent ID and packet-only handoff attestation')
    validate_result(result,packet)
    folder=Path(folder)
    if (folder/'lock.json').exists() or (folder/'result.json').exists():raise ValueError('Run already locked/partially locked; never overwrite. Start a new run.')
    once(folder/'result.json',result)
    receipt={'schema_version':1,'run_id':packet['run_id'],'packet_sha256':sha(packet),'result_sha256':sha(result),
             'prepared_at':meta['prepared_at'],'locked_at':now(),'agent_id':agent_id,
             'context_attestation':{'fresh_no_history':True,'packet_only_requested':True},'method':METHOD,'limitations':LIMITATION}
    once(folder/'lock.json',receipt)
    return receipt


def locked(folder):
    packet,meta=verify_run(folder)
    result=json.loads((Path(folder)/'result.json').read_text());receipt=json.loads((Path(folder)/'lock.json').read_text())
    validate_result(result,packet)
    if receipt['run_id']!=packet['run_id'] or receipt['packet_sha256']!=sha(packet) or receipt['result_sha256']!=sha(result):raise ValueError('Lock/result hash mismatch')
    if receipt.get('method')!=METHOD or receipt.get('prepared_at')!=meta['prepared_at'] or not receipt.get('agent_id') or receipt.get('context_attestation')!={'fresh_no_history':True,'packet_only_requested':True}:
        raise ValueError('Lock handoff attestation mismatch')
    if timestamp(receipt['locked_at'])<timestamp(receipt['prepared_at']):raise ValueError('Invalid lock chronology')
    return packet,meta,result,receipt


def compare(root, folder):
    packet,meta,result,receipt=locked(folder)
    record=json.loads((Path(root)/'data/properties'/f"{meta['slug']}.json").read_text())
    if record_sha(record)!=meta['record_subject_sha256']:raise ValueError('Subject facts changed; prepare a new blind pass')
    ask=record.get('current_list_price');number(ask,'current asking price',True)
    out={'run_id':packet['run_id'],'packet_sha256':sha(packet),'result_sha256':sha(result),
         'compared_at':now(),'asking_price':ask,'blind_status':result['status'],
         'difference_from_mid':ask-result['value_mid'] if result['status']=='valued' else None,
         'percent_above_mid':round((ask/result['value_mid']-1)*100,2) if result['status']=='valued' else None,
         'note':'Coordinator comparison after lock; valuation subagent is not sent the ask. This is not an automatic offer recommendation.'}
    once(Path(folder)/('comparison-'+uuid.uuid4().hex+'.json'),out)
    return out


def public_audit(root, folder, reviewed=False):
    if not reviewed:raise ValueError('Review packet/result for public sharing before --reviewed')
    packet,meta,result,receipt=locked(folder)
    root=Path(root);profile=json.loads((root/'buyer_profile.json').read_text())
    audit={'schema_version':1,'slug':meta['slug'],'record_subject_sha256':meta['record_subject_sha256'],
           'packet':packet,'result':result,'receipt':receipt}
    if private_content(canonical(audit),profile):raise ValueError('Private destination detected in public audit')
    record_path=root/'data/properties'/f"{meta['slug']}.json"
    record=json.loads(record_path.read_text())
    if record_sha(record)!=meta['record_subject_sha256']:raise ValueError('Subject facts changed; new pass needed')
    relative=Path('data/valuations')/meta['slug']/(packet['run_id']+'.json')
    target=root/relative
    if target.exists():
        if json.loads(target.read_text())!=audit:raise ValueError('Public run exists with different content')
    else:once(target,audit)
    record['blind_valuation']={'method':METHOD,'status':result['status'],'run_id':packet['run_id'],
        'audit_path':relative.as_posix(),'packet_sha256':sha(packet),'result_sha256':sha(result),
        'value_low':result['value_low'],'value_mid':result['value_mid'],'value_high':result['value_high'],
        'limitations':LIMITATION}
    write_json(record_path,record)
    return target


def check_record(root, record):
    meta=record.get('blind_valuation')
    if meta is None:return []  # Historical evaluations are not retroactively called blind.
    errors=[]
    try:
        if not isinstance(meta,dict) or meta.get('method')!=METHOD:raise ValueError('Unknown blinding method')
        if meta.get('status')=='pending':
            if record.get('research_status')!='draft':raise ValueError('Reviewed evaluation has no completed blind pass')
            return []
        if meta.get('status')=='unavailable':
            if not isinstance(meta.get('reason'),str) or not meta['reason'].strip():raise ValueError('Unavailable blinding needs a reason; do not claim blind results')
            return []
        run_id=meta.get('run_id','')
        if not re.fullmatch(r'[a-f0-9]{32}',run_id):raise ValueError('Invalid blind run ID')
        expected=f"data/valuations/{record['slug']}/{run_id}.json"
        if meta.get('audit_path')!=expected:raise ValueError('Invalid/cross-property audit path')
        audit=json.loads((Path(root)/expected).read_text())
        packet,result,receipt=audit['packet'],audit['result'],audit['receipt']
        validate_packet(packet);validate_result(result,packet)
        if audit['slug']!=record['slug'] or packet['run_id']!=run_id or audit['record_subject_sha256']!=record_sha(record):raise ValueError('Audit identity/subject facts mismatch')
        if receipt['method']!=METHOD or receipt['run_id']!=run_id or receipt['context_attestation']!={'fresh_no_history':True,'packet_only_requested':True} or not receipt['agent_id']:raise ValueError('Missing fresh-context handoff attestation')
        if timestamp(receipt['locked_at'])<timestamp(receipt['prepared_at']):raise ValueError('Bad audit chronology')
        for key,actual in [('packet_sha256',sha(packet)),('result_sha256',sha(result))]:
            if receipt[key]!=actual or meta[key]!=actual:raise ValueError('Public valuation audit hash mismatch')
        if meta['status']!=result['status'] or any(meta.get(k)!=result[k] for k in ('value_low','value_mid','value_high')):raise ValueError('Blind result metadata mismatch')
        if result['status']=='valued' and (record.get('estimated_value_low'),record.get('estimated_value_high'))!=(result['value_low'],result['value_high']):
            revision=record.get('valuation_revision',{})
            if not revision.get('reason') or not revision.get('new_evidence') or revision.get('original_run_id')!=run_id:
                raise ValueError('Final range differs from locked blind range; document valuation_revision reason/new_evidence/original_run_id')
    except (ValueError,KeyError,TypeError,OSError) as exc:errors.append('Blind valuation: '+str(exc))
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    sub=parser.add_subparsers(dest='command',required=True)
    make=sub.add_parser('prepare');make.add_argument('--slug',required=True);make.add_argument('--input',required=True)
    make.add_argument('--reviewed',action='store_true');make.add_argument('--profile')
    save=sub.add_parser('lock');save.add_argument('--run-dir',required=True);save.add_argument('--result',required=True)
    save.add_argument('--agent-id',required=True);save.add_argument('--fresh-context',action='store_true');save.add_argument('--packet-only',action='store_true')
    for name in ('verify','compare','publish'):
        cmd=sub.add_parser(name);cmd.add_argument('--run-dir',required=True)
        if name=='publish':cmd.add_argument('--reviewed',action='store_true')
    args=parser.parse_args()
    if args.command=='prepare':print(prepare(args.root,args.slug,json.loads(Path(args.input).read_text()),args.reviewed,args.profile))
    elif args.command=='lock':print(json.dumps(lock(args.run_dir,json.loads(Path(args.result).read_text()),args.agent_id,args.fresh_context,args.packet_only),indent=2))
    elif args.command=='verify':
        packet,meta,result,receipt=locked(args.run_dir);print(json.dumps({'run_id':packet['run_id'],'status':result['status'],'hashes_verified':True,'limitations':LIMITATION},indent=2))
    elif args.command=='compare':print(json.dumps(compare(args.root,args.run_dir),indent=2))
    else:print(public_audit(args.root,args.run_dir,args.reviewed))


if __name__=='__main__':main()
