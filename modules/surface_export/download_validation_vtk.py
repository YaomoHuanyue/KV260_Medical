"""Recover truncated downloads using checked HTTP ranges and the official SHA."""
from pathlib import Path
import hashlib,json,time,urllib.request,urllib.parse

HERE=Path(__file__).resolve().parent
def main():
    metadata=HERE/'results/VTK_official_package_metadata_r1.json'
    entry=json.loads(metadata.read_text());size=entry['size'];url=entry['url']
    assert urllib.parse.urlparse(url).hostname=='files.pythonhosted.org'
    assert entry['filename']=='vtk-9.7.1-cp312-cp312-win_amd64.whl'
    assert entry['digests']['sha256']=='64a50b972240f477c864a0d16dfc247e7f540b007ec4016b76cb8f112f62a66b'
    folder=HERE/'build';folder.mkdir(exist_ok=True)
    target=folder/entry['filename'];pending=target.with_suffix('.partial')
    assert not target.exists() and not pending.exists()
    receipts=[];digest=hashlib.sha256();start=time.monotonic()
    with pending.open('xb') as stream:
        for offset in range(0,size,4*1024*1024):
            end=min(size-1,offset+4*1024*1024-1)
            for attempt in range(3):
                try:
                    request=urllib.request.Request(url,headers={'Range':f'bytes={offset}-{end}'})
                    with urllib.request.urlopen(request,timeout=30) as response:
                        assert response.status==206
                        assert response.headers['Content-Range']==f'bytes {offset}-{end}/{size}'
                        chunk=response.read(end-offset+2)
                    assert len(chunk)==end-offset+1
                    break
                except Exception:
                    if attempt==2:raise
            stream.write(chunk);digest.update(chunk)
            receipts.append(dict(start=offset,end=end,bytes=len(chunk),sha256=hashlib.sha256(chunk).hexdigest()))
            print('Verified range',offset,end,flush=True)
    assert digest.hexdigest()==entry['digests']['sha256']
    pending.rename(target)
    record=dict(status='all_ranges_and_final_official_PyPI_SHA_verified',size_bytes=size,
        sha256=digest.hexdigest(),elapsed_seconds=time.monotonic()-start,
        ranges=receipts,verification_relaxed=False,
        downloader_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        metadata_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest())
    p=HERE/'results/VTK_range_download_r1.json';assert not p.exists()
    p.write_text(json.dumps(record,indent=2)+'\n')
    print(record['status'],flush=True)

if __name__=='__main__':main()
