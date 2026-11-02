"""Fetch prespecified AeroPath cases from the official ZIP with HTTP ranges and CRC checks."""
import argparse,hashlib,json,struct,time,zlib
from pathlib import Path
import requests
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
URL='https://zenodo.org/records/10069289/files/AeroPath.zip?download=1'

def get_range(start,end,stream=False):
    for attempt in range(3):
        try:
            r=requests.get(URL,headers={'Range':f'bytes={start}-{end}'},stream=stream,timeout=(15,60))
            r.raise_for_status()
            if r.status_code!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
                r.close();raise RuntimeError('Server did not honor the exact byte range')
            return r
        except requests.RequestException:
            if attempt==2:raise
            time.sleep(2**attempt)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',nargs='+',default=['1','2','3'])
    p.add_argument('--manifest',default='source_manifest.json')
    p.add_argument('--purpose',default='frozen student external evaluation; never train on these cases in this experiment')
    p.add_argument('--connections',type=int,default=4)
    a=p.parse_args()
    if any(not c.isdigit() or not 1<=int(c)<=27 for c in a.cases):raise ValueError('Invalid AeroPath case')
    if Path(a.manifest).name!=a.manifest:raise ValueError('Manifest must be a filename')
    if not 1<=a.connections<=4:raise ValueError('Use 1 to 4 download connections')
    index=json.loads((ROOT/'outputs/ct_segmentation_audit/aeropath_index.json').read_text())
    out=ROOT/'resources/public_ct/aeropath';out.mkdir(parents=True,exist_ok=True)
    selection=[f for f in index if f['size'] and (f['name'] in ['AeroPath/license.md','AeroPath/README.md'] or f['name'].split('/')[1] in a.cases)]
    manifest={'source':URL,'prespecified_cases':a.cases,'purpose':a.purpose,'files':[]}
    for f in selection:
        rel=Path(*Path(f['name']).parts[1:]);dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and dest.stat().st_size==f['size']:
            data=dest.read_bytes();assert zlib.crc32(data)==f['crc']
        else:
            head=get_range(f['offset'],f['offset']+29).content
            assert head[:4]==b'PK\x03\x04'
            nl,el=struct.unpack_from('<HH',head,26);start=f['offset']+30+nl+el
            temp=dest.with_suffix(dest.suffix+'.part');crc=0;total=0
            decoder=zlib.decompressobj(-15) if f['compress_type']==8 else None
            chunk=8*1024*1024
            spans=[(s,min(s+chunk,start+f['compressed'])-1) for s in range(start,start+f['compressed'],chunk)]
            def fetch(span):
                with get_range(*span) as response:return response.content
            with ThreadPoolExecutor(max_workers=a.connections) as pool,temp.open('wb') as output:
                for num,block in enumerate(pool.map(fetch,spans),1):
                    data=decoder.decompress(block) if decoder else block
                    output.write(data);crc=zlib.crc32(data,crc);total+=len(data)
                    if num%4==0:print('downloaded',rel,total,'bytes',flush=True)
            if decoder:
                assert decoder.eof
            assert total==f['size'] and crc==f['crc'],(f['name'],total,crc)
            temp.replace(dest)
        digest=hashlib.sha256(dest.read_bytes()).hexdigest()
        manifest['files'].append({**f,'relative_path':str(rel),'sha256':digest})
        (out/a.manifest).write_text(json.dumps(manifest,indent=2),encoding='utf8')
        print('verified',rel,flush=True)
    print('completed',flush=True)

if __name__=='__main__':main()
