"""Read the exact complete seven-case formal FMA2 stimulus and gold banks."""
from pathlib import Path
import hashlib,json,re,zipfile
PREFIX='workspace/dfx/smooth_speed/shared_fma2_fixture_r1/hls/sim/tv/cdatafile/'
NAMES=['row_mem','meta','graph','face_mem','coords','original','rows','edges','frozen','faces',
    'current','half','candidate','lap','next_lap','report_r','nv','nf','nnz','limit','iterations']
GOLD_SHA256='e824be152e4da87120b2cc980390d6f647b55f8333914472f96638b9145d77bf'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def transactions(z,name,expected):
    pages=[];state='runtime';h=hashlib.sha256()
    with z.open(name) as stream:
        for raw in stream:
            h.update(raw);token=raw.decode('ascii').strip()
            if not token:continue
            if state=='runtime':assert token=='[[[runtime]]]';state='transaction'
            elif state=='transaction':
                if token=='[[[/runtime]]]':state='end'
                else:
                    match=re.fullmatch(r'\[\[transaction\]\]\s+(\d+)',token)
                    assert match and int(match[1])==len(pages);pages.append([]);state='data'
            elif state=='data':
                if token=='[[/transaction]]':state='transaction'
                else:pages[-1].append(int(token,16 if token.startswith('0x') else 10))
            else:raise AssertionError('Trailing fixture bytes')
    assert state=='end' and len(pages)==7 and h.hexdigest()==expected,name
    return pages
def load(archive):
    assert sha(archive)==GOLD_SHA256
    values={};bindings={}
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('outputs_manifest.json'))
        for key in NAMES+['gold_meta','gold_coords']:
            suffix='autotvout_'+key[5:] if key.startswith('gold_') else 'autotvin_'+key
            member=PREFIX+'c.mesh_smooth.'+suffix+'.dat';assert member in manifest,member
            values[key]=transactions(z,member,manifest[member]);bindings[member]=manifest[member]
    for case in range(7):
        for n in NAMES[5:]:assert len(values[n][case])==1,n
        assert len(values['gold_meta'][case])==131090 and len(values['gold_coords'][case])==327685
    return values,bindings
